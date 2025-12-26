import pandas as pd
from datetime import date, timedelta
import psycopg2
import streamlit as st

@st.cache_resource(ttl=3600, validate=lambda conn: conn.closed == 0)
def get_connection_cached(db_url):
    return psycopg2.connect(db_url)

def connect_db():
    if 'db_url' not in st.session_state or not st.session_state['db_url']:
        return None
    try:
        return get_connection_cached(st.session_state['db_url'])
    except Exception:
        st.cache_resource.clear()
        return get_connection_cached(st.session_state['db_url'])

def init_db():
    conn = connect_db()
    if not conn: return
    
    with conn.cursor() as cur:
        cur.execute('''CREATE TABLE IF NOT EXISTS logi 
                        (id SERIAL PRIMARY KEY, data TEXT, aktywnosc TEXT, ilosc REAL)''')
        
        cur.execute('''CREATE TABLE IF NOT EXISTS cele 
                        (klucz_tygodnia TEXT, aktywnosc TEXT, wartosc REAL, 
                        PRIMARY KEY (klucz_tygodnia, aktywnosc))''')
        
        cur.execute('''CREATE TABLE IF NOT EXISTS config_aktywnosci 
                        (nazwa TEXT PRIMARY KEY, kategoria TEXT, czy_zly INTEGER)''')
        
        cur.execute('''CREATE TABLE IF NOT EXISTS biegi 
                        (id SERIAL PRIMARY KEY, data TEXT, dystans REAL, czas_min REAL, tempo_min_km REAL, notatka TEXT)''')
        
        conn.commit()
        
        cur.execute("SELECT count(*) FROM config_aktywnosci")
        if cur.fetchone()[0] == 0:
            data = [
                ("Pushups", "Workouts", 0), ("Pullups", "Workouts", 0), 
                ("Pool (laps)", "Workouts", 0), ("Running (km)", "Workouts", 0), ("Running (pace)", "Workouts", 0),
                ("Coffee", "Bad Habits", 1), ("Sweets", "Bad Habits", 1), ("Junk Food", "Bad Habits", 1), ("Alcohol", "Bad Habits", 1),
                ("Sauna (min)", "Recovery", 0), ("Supplements", "Recovery", 0),
                ("5", "Bouldering", 0), ("6A", "Bouldering", 0), ("6A+", "Bouldering", 0), ("6B", "Bouldering", 0), ("6C", "Bouldering", 0),
                ("5", "Sport Climbing", 0), ("6a", "Sport Climbing", 0), ("6a+", "Sport Climbing", 0), ("6b", "Sport Climbing", 0)
            ]
            query = "INSERT INTO config_aktywnosci (nazwa, kategoria, czy_zly) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING"
            cur.executemany(query, data)
            conn.commit()

def undo_last_log():
    conn = connect_db()
    msg = None
    with conn.cursor() as cur:
        cur.execute("SELECT id, aktywnosc, ilosc FROM logi ORDER BY id DESC LIMIT 1")
        last = cur.fetchone()
        
        if last:
            cur.execute("DELETE FROM logi WHERE id = %s", (last[0],))
            conn.commit()
            msg = f"{last[1]} ({last[2]})"
    return msg

def add_run(distance, time_min, note="", run_date=None):
    if run_date is None: run_date = str(date.today())
    else: run_date = str(run_date)
    pace = time_min / distance if distance > 0 else 0
    
    conn = connect_db()
    with conn.cursor() as cur:
        cur.execute("INSERT INTO biegi (data, dystans, czas_min, tempo_min_km, notatka) VALUES (%s, %s, %s, %s, %s)", 
                      (run_date, distance, time_min, pace, note))
        cur.execute("INSERT INTO logi (data, aktywnosc, ilosc) VALUES (%s, %s, %s)", (run_date, "Running (km)", distance))
        cur.execute("INSERT INTO logi (data, aktywnosc, ilosc) VALUES (%s, %s, %s)", (run_date, "Running (pace)", pace))
        conn.commit()

def update_run(run_id, column, new_value):
    conn = connect_db()
    col_map = {"distance": "dystans", "time_min": "czas_min", "note": "notatka", "date": "data"}
    db_col = col_map.get(column, column)
    
    allowed = ["dystans", "czas_min", "notatka", "data"]
    if db_col not in allowed: return

    with conn.cursor() as cur:
        query = f"UPDATE biegi SET {db_col} = %s WHERE id = %s"
        cur.execute(query, (new_value, run_id))
        if db_col in ['dystans', 'czas_min']:
            cur.execute("UPDATE biegi SET tempo_min_km = czas_min / dystans WHERE id = %s", (run_id,))
        conn.commit()

def delete_run(run_id):
    conn = connect_db()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM biegi WHERE id = %s", (run_id,))
        conn.commit()

def get_run_history():
    conn = connect_db()
    query = """
    SELECT id, data as date, dystans as distance, czas_min as time_min, tempo_min_km as pace, notatka as note 
    FROM biegi ORDER BY data DESC, id DESC
    """
    return pd.read_sql_query(query, conn)

def get_sql_date_range(period):
    today = date.today()
    if period == "This Week": start = today - timedelta(days=today.weekday())
    elif period == "This Month": start = today.replace(day=1)
    elif period == "This Year": start = today.replace(month=1, day=1)
    else: start = today
    return str(start)

def get_week_key(d=None):
    if d is None: d = date.today()
    return f"{d.year}-{d.isocalendar()[1]}"

def get_weeks_in_period(period):
    today = date.today()
    keys = set()
    if period == "This Week": start = today - timedelta(days=today.weekday())
    elif period == "This Month": start = today.replace(day=1)
    elif period == "This Year": start = today.replace(month=1, day=1)
    else: start = today
    current = start
    while current <= today:
        keys.add(f"{current.year}-{current.isocalendar()[1]}")
        current += timedelta(days=7)
    keys.add(f"{today.year}-{today.isocalendar()[1]}")
    return list(keys)

def calc_historical_goal(activity, period):
    keys = get_weeks_in_period(period)
    if not keys: return 0
    conn = connect_db()
    with conn.cursor() as cur:
        placeholders = ','.join('%s' for _ in keys)
        query = f"SELECT SUM(wartosc) FROM cele WHERE aktywnosc = %s AND klucz_tygodnia IN ({placeholders})"
        cur.execute(query, [activity] + keys)
        result = cur.fetchone()[0]
    return result if result else 0

@st.cache_data(ttl=600) 
def get_config():
    conn = connect_db()
    return pd.read_sql_query("SELECT nazwa as name, kategoria as category, czy_zly as is_bad FROM config_aktywnosci", conn)

def get_full_planner():
    conn = connect_db()
    key = get_week_key()
    query = """
    SELECT c.nazwa as "Activity", c.kategoria as "Category", c.czy_zly as "Is Bad Habit", COALESCE(t.wartosc, 0) as "Weekly Goal"
    FROM config_aktywnosci c
    LEFT JOIN cele t ON c.nazwa = t.aktywnosc AND t.klucz_tygodnia = %s
    ORDER BY c.kategoria, c.nazwa
    """
    return pd.read_sql_query(query, conn, params=(key,))

def update_planner_batch(changes, df_snapshot):
    conn = connect_db()
    key = get_week_key()
    
    with conn.cursor() as cur:
        for idx in changes["deleted_rows"]:
            if idx < len(df_snapshot):
                act_name = df_snapshot.iloc[idx]['Activity']
                cur.execute("DELETE FROM config_aktywnosci WHERE nazwa = %s", (act_name,))
                cur.execute("DELETE FROM cele WHERE aktywnosc = %s", (act_name,))
            
        for idx, row_changes in changes["edited_rows"].items():
            if idx < len(df_snapshot):
                original_row = df_snapshot.iloc[idx]
                act_name = original_row['Activity']
                
                if "Category" in row_changes or "Is Bad Habit" in row_changes:
                    new_cat = row_changes.get("Category", original_row['Category'])
                    bad_val = row_changes.get("Is Bad Habit", original_row['Is Bad Habit'])
                    new_bad = 1 if (bad_val is True or bad_val == 1) else 0
                    cur.execute("UPDATE config_aktywnosci SET kategoria=%s, czy_zly=%s WHERE nazwa=%s", 
                                (new_cat, new_bad, act_name))
                
                if "Weekly Goal" in row_changes:
                    new_goal = row_changes["Weekly Goal"]
                    query_goal = """
                        INSERT INTO cele (klucz_tygodnia, aktywnosc, wartosc) VALUES (%s, %s, %s)
                        ON CONFLICT (klucz_tygodnia, aktywnosc) DO UPDATE SET wartosc = EXCLUDED.wartosc
                    """
                    cur.execute(query_goal, (key, act_name, new_goal))

        for new_row in changes["added_rows"]:
            raw_name = new_row.get("Activity", "")
            name = raw_name.strip() if raw_name else None
            
            raw_cat = new_row.get("Category", "")
            cat = raw_cat.strip() if raw_cat else None
            
            bad_val = new_row.get("Is Bad Habit", False)
            bad = 1 if (bad_val is True or bad_val == 1) else 0
            
            goal = new_row.get("Weekly Goal", 0)
            
            if name and cat:
                query_ins = """
                    INSERT INTO config_aktywnosci (nazwa, kategoria, czy_zly) VALUES (%s, %s, %s)
                    ON CONFLICT (nazwa) DO UPDATE SET kategoria = EXCLUDED.kategoria, czy_zly = EXCLUDED.czy_zly
                """
                cur.execute(query_ins, (name, cat, bad))
                
                if goal > 0:
                    query_goal = """
                        INSERT INTO cele (klucz_tygodnia, aktywnosc, wartosc) VALUES (%s, %s, %s)
                        ON CONFLICT (klucz_tygodnia, aktywnosc) DO UPDATE SET wartosc = EXCLUDED.wartosc
                    """
                    cur.execute(query_goal, (key, name, goal))

        conn.commit()
    st.cache_data.clear()

def add_log(activity, amount):
    conn = connect_db()
    with conn.cursor() as cur:
        cur.execute("INSERT INTO logi (data, aktywnosc, ilosc) VALUES (%s, %s, %s)", (str(date.today()), activity, amount))
        conn.commit()

def get_weekly_state_dict():
    conn = connect_db()
    start = get_sql_date_range("This Week")
    df = pd.read_sql_query("SELECT aktywnosc, SUM(ilosc) as suma FROM logi WHERE data >= %s GROUP BY aktywnosc", conn, params=(start,))
    if df.empty: return {}
    return dict(zip(df.aktywnosc, df.suma))

def get_current_goals_dict():
    conn = connect_db()
    df = pd.read_sql_query("SELECT aktywnosc, wartosc FROM cele WHERE klucz_tygodnia = %s", conn, params=(get_week_key(),))
    if df.empty: return {}
    return dict(zip(df.aktywnosc, df.wartosc))

def get_chart_data(activity_list, period):
    if not activity_list: return pd.DataFrame(columns=['data', 'aktywnosc', 'ilosc'])
    conn = connect_db()
    start = get_sql_date_range(period)
    placeholders = ','.join('%s' for _ in activity_list)
    query = f"SELECT data, aktywnosc, ilosc FROM logi WHERE data >= %s AND aktywnosc IN ({placeholders})"
    params = [start] + activity_list
    df = pd.read_sql_query(query, conn, params=params)
    return df

def rename_category_in_db(old_name, new_name):
    conn = connect_db()
    with conn.cursor() as cur:
        cur.execute("UPDATE config_aktywnosci SET kategoria = %s WHERE kategoria = %s", (new_name, old_name))
        conn.commit()
    st.cache_data.clear()