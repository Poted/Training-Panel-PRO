import os
import pandas as pd
from datetime import date, datetime, timedelta
import psycopg2
import streamlit as st

# --- CACHE POŁĄCZENIA (TO JEST TURBO DOŁADOWANIE) ---
# Ta funkcja uruchomi się tylko raz dla danego URL i będzie trzymać otwarte połączenie
@st.cache_resource(ttl=3600, validate=lambda conn: conn.closed == 0)
def get_connection_cached(db_url):
    return psycopg2.connect(db_url)

def polacz():
    if 'db_url' not in st.session_state or not st.session_state['db_url']:
        return None
    
    # Zamiast tworzyć nowe, bierzemy z cache
    try:
        return get_connection_cached(st.session_state['db_url'])
    except Exception as e:
        # Jeśli cache padł, czyścimy i próbujemy jeszcze raz (autonaprawa)
        st.cache_resource.clear()
        return get_connection_cached(st.session_state['db_url'])

# --- INICJALIZACJA ---
def inicjalizuj_baze():
    conn = polacz()
    if not conn: return
    
    # Używamy context managera dla kursora, ale NIE zamykamy połączenia (conn)
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
        
        # Seedowanie
        cur.execute("SELECT count(*) FROM config_aktywnosci")
        if cur.fetchone()[0] == 0:
            dane = [("Pompki", "Treningi", 0), ("Podciągnięcia", "Treningi", 0), 
                    ("Basen (długości)", "Treningi", 0), ("Bieganie (km)", "Treningi", 0), ("Bieganie (tempo)", "Treningi", 0),
                    ("Kawa", "Używki", 1), ("Słodycze", "Używki", 1), ("Junk Food", "Używki", 1), ("Alkohol", "Używki", 1),
                    ("Sauna (min)", "Regeneracja", 0), ("Suplementy", "Regeneracja", 0),
                    ("5", "Baldy", 0), ("6A", "Baldy", 0), ("6A+", "Baldy", 0), ("6B", "Baldy", 0), ("6C", "Baldy", 0), ("7A", "Baldy", 0),
                    ("5", "Liny", 0), ("6a", "Liny", 0), ("6a+", "Liny", 0), ("6b", "Liny", 0), ("6c", "Liny", 0), ("7a", "Liny", 0)]
            
            query = "INSERT INTO config_aktywnosci (nazwa, kategoria, czy_zly) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING"
            cur.executemany(query, dane)
            conn.commit()

# --- UNDO ---
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

# --- POZOSTAŁE FUNKCJE ---
def dodaj_bieg(dystans, czas_min, notatka="", data_biegu=None):
    if data_biegu is None: data_biegu = str(date.today())
    else: data_biegu = str(data_biegu)
    tempo = czas_min / dystans if dystans > 0 else 0
    
    conn = polacz()
    with conn.cursor() as cur:
        cur.execute("INSERT INTO biegi (data, dystans, czas_min, tempo_min_km, notatka) VALUES (%s, %s, %s, %s, %s)", 
                     (data_biegu, dystans, czas_min, tempo, notatka))
        cur.execute("INSERT INTO logi (data, aktywnosc, ilosc) VALUES (%s, %s, %s)", (data_biegu, "Bieganie (km)", dystans))
        cur.execute("INSERT INTO logi (data, aktywnosc, ilosc) VALUES (%s, %s, %s)", (data_biegu, "Bieganie (tempo)", tempo))
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
    # pandas read_sql nie zamyka conn automatycznie, więc jest bezpieczne
    return pd.read_sql_query("SELECT * FROM biegi ORDER BY data DESC, id DESC", conn)

def daj_zakres_dat_sql(okres):
    dzis = date.today()
    if okres == "Ten Tydzień": start = dzis - timedelta(days=dzis.weekday())
    elif okres == "Ten Miesiąc": start = dzis.replace(day=1)
    elif okres == "Ten Rok": start = dzis.replace(month=1, day=1)
    else: start = dzis
    return str(start)

def daj_klucz_tygodnia(d=None):
    if d is None: d = date.today()
    return f"{d.year}-{d.isocalendar()[1]}"

def daj_liste_tygodni_w_okresie(okres):
    dzis = date.today()
    klucze = set()
    if okres == "Ten Tydzień": start = dzis - timedelta(days=dzis.weekday())
    elif okres == "Ten Miesiąc": start = dzis.replace(day=1)
    elif okres == "Ten Rok": start = dzis.replace(month=1, day=1)
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

# Cache dla konfiguracji, bo to się rzadko zmienia
@st.cache_data(ttl=600) 
def pobierz_konfiguracje():
    conn = polacz()
    return pd.read_sql_query("SELECT * FROM config_aktywnosci", conn)

def dodaj_nowa_aktywnosc(nazwa, kategoria, czy_zly):
    conn = polacz()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO config_aktywnosci VALUES (%s, %s, %s)", (nazwa, kategoria, 1 if czy_zly else 0))
            conn.commit()
        st.cache_data.clear() # Czyścimy cache konfiguracji po zmianie
        return True
    except: return False

def usun_aktywnosc(nazwa):
    conn = polacz()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM config_aktywnosci WHERE nazwa = %s", (nazwa,))
        conn.commit()
    st.cache_data.clear()

def dodaj_log(aktywnosc, ilosc):
    conn = polacz()
    with conn.cursor() as cur:
        cur.execute("INSERT INTO logi (data, aktywnosc, ilosc) VALUES (%s, %s, %s)", (str(date.today()), aktywnosc, ilosc))
        conn.commit()

def ustaw_cel(aktywnosc, wartosc):
    conn = polacz()
    with conn.cursor() as cur:
        query = """
            INSERT INTO cele (klucz_tygodnia, aktywnosc, wartosc) 
            VALUES (%s, %s, %s)
            ON CONFLICT (klucz_tygodnia, aktywnosc) 
            DO UPDATE SET wartosc = EXCLUDED.wartosc
        """
        cur.execute(query, (daj_klucz_tygodnia(), aktywnosc, wartosc))
        conn.commit()

def pobierz_stan_tygodnia_dict():
    conn = polacz()
    start = daj_zakres_dat_sql("Ten Tydzień")
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