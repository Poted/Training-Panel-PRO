import os
import pandas as pd
from datetime import date, datetime, timedelta
import psycopg2
import streamlit as st

@st.cache_resource(ttl=3600, validate=lambda conn: conn.closed == 0)
def get_connection_cached(db_url):
    return psycopg2.connect(db_url)

def polacz():
    if 'db_url' not in st.session_state or not st.session_state['db_url']:
        return None
    try:
        return get_connection_cached(st.session_state['db_url'])
    except Exception as e:
        st.cache_resource.clear()
        return get_connection_cached(st.session_state['db_url'])

def inicjalizuj_baze():
    conn = polacz()
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
            dane = [
                ("Pushups", "Workouts", 0), ("Pullups", "Workouts", 0), 
                ("Pool (laps)", "Workouts", 0), ("Running (km)", "Workouts", 0), ("Running (pace)", "Workouts", 0),
                ("Coffee", "Bad Habits", 1), ("Sweets", "Bad Habits", 1), ("Junk Food", "Bad Habits", 1), ("Alcohol", "Bad Habits", 1),
                ("Sauna (min)", "Recovery", 0), ("Supplements", "Recovery", 0),
                ("5", "Bouldering", 0), ("6A", "Bouldering", 0), ("6A+", "Bouldering", 0), ("6B", "Bouldering", 0), ("6C", "Bouldering", 0),
                ("5", "Sport Climbing", 0), ("6a", "Sport Climbing", 0), ("6a+", "Sport Climbing", 0), ("6b", "Sport Climbing", 0)
            ]
            
            query = "INSERT INTO config_aktywnosci (nazwa, kategoria, czy_zly) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING"
            cur.executemany(query, dane)
            conn.commit()

def cofnij_ostatni_log():
    conn = polacz()
    msg = None
    with conn.cursor() as cur:
        cur.execute("SELECT id, aktywnosc, ilosc FROM logi ORDER BY id DESC LIMIT 1")
        ostatni = cur.fetchone()
        
        if ostatni:
            cur.execute("DELETE FROM logi WHERE id = %s", (ostatni[0],))
            conn.commit()
            msg = f"{ostatni[1]} ({ostatni[2]})"
    return msg

def dodaj_bieg(dystans, czas_min, notatka="", data_biegu=None):
    if data_biegu is None: data_biegu = str(date.today())
    else: data_biegu = str(data_biegu)
    tempo = czas_min / dystans if dystans > 0 else 0
    
    conn = polacz()
    with conn.cursor() as cur:
        cur.execute("INSERT INTO biegi (data, dystans, czas_min, tempo_min_km, notatka) VALUES (%s, %s, %s, %s, %s)", 
                      (data_biegu, dystans, czas_min, tempo, notatka))
        cur.execute("INSERT INTO logi (data, aktywnosc, ilosc) VALUES (%s, %s, %s)", (data_biegu, "Running (km)", dystans))
        cur.execute("INSERT INTO logi (data, aktywnosc, ilosc) VALUES (%s, %s, %s)", (data_biegu, "Running (pace)", tempo))
        conn.commit()

def aktualizuj_bieg(id_biegu, kolumna, nowa_wartosc):
    conn = polacz()
    dozwolone = ["dystans", "czas_min", "notatka", "data"]
    if kolumna not in dozwolone: return

    with conn.cursor() as cur:
        query = f"UPDATE biegi SET {kolumna} = %s WHERE id = %s"
        cur.execute(query, (nowa_wartosc, id_biegu))
        if kolumna in ['dystans', 'czas_min']:
            cur.execute("UPDATE biegi SET tempo_min_km = czas_min / dystans WHERE id = %s", (id_biegu,))
        conn.commit()

def usun_bieg(id_biegu):
    conn = polacz()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM biegi WHERE id = %s", (id_biegu,))
        conn.commit()

def pobierz_historie_biegow():
    conn = polacz()
    return pd.read_sql_query("SELECT * FROM biegi ORDER BY data DESC, id DESC", conn)

def daj_zakres_dat_sql(okres):
    dzis = date.today()
    if okres == "This Week": start = dzis - timedelta(days=dzis.weekday())
    elif okres == "This Month": start = dzis.replace(day=1)
    elif okres == "This Year": start = dzis.replace(month=1, day=1)
    else: start = dzis
    return str(start)

def daj_klucz_tygodnia(d=None):
    if d is None: d = date.today()
    return f"{d.year}-{d.isocalendar()[1]}"

def daj_liste_tygodni_w_okresie(okres):
    dzis = date.today()
    klucze = set()
    if okres == "This Week": start = dzis - timedelta(days=dzis.weekday())
    elif okres == "This Month": start = dzis.replace(day=1)
    elif okres == "This Year": start = dzis.replace(month=1, day=1)
    else: start = dzis
    current = start
    while current <= dzis:
        klucze.add(f"{current.year}-{current.isocalendar()[1]}")
        current += timedelta(days=7)
    klucze.add(f"{dzis.year}-{dzis.isocalendar()[1]}")
    return list(klucze)

def oblicz_cel_historyczny(aktywnosc, okres):
    klucze = daj_liste_tygodni_w_okresie(okres)
    if not klucze: return 0
    conn = polacz()
    with conn.cursor() as cur:
        placeholders = ','.join('%s' for _ in klucze)
        query = f"SELECT SUM(wartosc) FROM cele WHERE aktywnosc = %s AND klucz_tygodnia IN ({placeholders})"
        cur.execute(query, [aktywnosc] + klucze)
        wynik = cur.fetchone()[0]
    return wynik if wynik else 0

@st.cache_data(ttl=600) 
def pobierz_konfiguracje():
    conn = polacz()
    return pd.read_sql_query("SELECT * FROM config_aktywnosci", conn)

def pobierz_pelny_planer():
    conn = polacz()
    klucz = daj_klucz_tygodnia()
    query = """
    SELECT c.nazwa as "Activity", c.kategoria as "Category", c.czy_zly as "Is Bad Habit", COALESCE(t.wartosc, 0) as "Weekly Goal"
    FROM config_aktywnosci c
    LEFT JOIN cele t ON c.nazwa = t.aktywnosc AND t.klucz_tygodnia = %s
    ORDER BY c.kategoria, c.nazwa
    """
    return pd.read_sql_query(query, conn, params=(klucz,))

def aktualizuj_planer_batch(changes, df_snapshot):
    conn = polacz()
    klucz = daj_klucz_tygodnia()
    
    with conn.cursor() as cur:
        for idx in changes["deleted_rows"]:
            act_name = df_snapshot.iloc[idx]['Activity']
            cur.execute("DELETE FROM config_aktywnosci WHERE nazwa = %s", (act_name,))
            cur.execute("DELETE FROM cele WHERE aktywnosc = %s", (act_name,))
            
        for idx, row_changes in changes["edited_rows"].items():
            original_row = df_snapshot.iloc[idx]
            act_name = original_row['Activity']
            
            if "Category" in row_changes or "Is Bad Habit" in row_changes:
                new_cat = row_changes.get("Category", original_row['Category'])
                new_bad = row_changes.get("Is Bad Habit", original_row['Is Bad Habit'])
                cur.execute("UPDATE config_aktywnosci SET kategoria=%s, czy_zly=%s WHERE nazwa=%s", 
                            (new_cat, 1 if new_bad else 0, act_name))
            
            if "Weekly Goal" in row_changes:
                new_goal = row_changes["Weekly Goal"]
                query_cel = """
                    INSERT INTO cele (klucz_tygodnia, aktywnosc, wartosc) VALUES (%s, %s, %s)
                    ON CONFLICT (klucz_tygodnia, aktywnosc) DO UPDATE SET wartosc = EXCLUDED.wartosc
                """
                cur.execute(query_cel, (klucz, act_name, new_goal))

        for new_row in changes["added_rows"]:
            nazwa = new_row.get("Activity")
            kat = new_row.get("Category")
            bad = new_row.get("Is Bad Habit", False)
            goal = new_row.get("Weekly Goal", 0)
            
            if nazwa and kat:
                try:
                    cur.execute("INSERT INTO config_aktywnosci (nazwa, kategoria, czy_zly) VALUES (%s, %s, %s)", 
                                (nazwa, kat, 1 if bad else 0))
                    if goal > 0:
                        query_cel = """
                            INSERT INTO cele (klucz_tygodnia, aktywnosc, wartosc) VALUES (%s, %s, %s)
                            ON CONFLICT (klucz_tygodnia, aktywnosc) DO UPDATE SET wartosc = EXCLUDED.wartosc
                        """
                        cur.execute(query_cel, (klucz, nazwa, goal))
                except Exception:
                    pass

        conn.commit()
    st.cache_data.clear()

def dodaj_nowa_aktywnosc(nazwa, kategoria, czy_zly):
    conn = polacz()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO config_aktywnosci VALUES (%s, %s, %s)", (nazwa, kategoria, 1 if czy_zly else 0))
            conn.commit()
        st.cache_data.clear()
        return True
    except: return False

def dodaj_log(aktywnosc, ilosc):
    conn = polacz()
    with conn.cursor() as cur:
        cur.execute("INSERT INTO logi (data, aktywnosc, ilosc) VALUES (%s, %s, %s)", (str(date.today()), aktywnosc, ilosc))
        conn.commit()

def pobierz_stan_tygodnia_dict():
    conn = polacz()
    start = daj_zakres_dat_sql("This Week")
    df = pd.read_sql_query("SELECT aktywnosc, SUM(ilosc) as suma FROM logi WHERE data >= %s GROUP BY aktywnosc", conn, params=(start,))
    if df.empty: return {}
    return dict(zip(df.aktywnosc, df.suma))

def pobierz_cele_biezace_dict():
    conn = polacz()
    df = pd.read_sql_query("SELECT aktywnosc, wartosc FROM cele WHERE klucz_tygodnia = %s", conn, params=(daj_klucz_tygodnia(),))
    if df.empty: return {}
    return dict(zip(df.aktywnosc, df.wartosc))

def pobierz_dane_wykres(lista, okres):
    if not lista: return pd.DataFrame(columns=['data', 'aktywnosc', 'ilosc'])
    conn = polacz()
    start = daj_zakres_dat_sql(okres)
    placeholders = ','.join('%s' for _ in lista)
    query = f"SELECT data, aktywnosc, ilosc FROM logi WHERE data >= %s AND aktywnosc IN ({placeholders})"
    params = [start] + lista
    df = pd.read_sql_query(query, conn, params=params)
    return df