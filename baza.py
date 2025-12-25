import sqlite3
from datetime import date, datetime, timedelta
import pandas as pd

DB_NAME = "treningi.db"

def polacz():
    return sqlite3.connect(DB_NAME)

# --- INICJALIZACJA ---
def inicjalizuj_baze():
    conn = polacz()
    conn.execute('''CREATE TABLE IF NOT EXISTS logi 
                    (id INTEGER PRIMARY KEY, data TEXT, aktywnosc TEXT, ilosc REAL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS cele 
                    (klucz_tygodnia TEXT, aktywnosc TEXT, wartosc REAL, 
                    PRIMARY KEY (klucz_tygodnia, aktywnosc))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS config_aktywnosci 
                    (nazwa TEXT PRIMARY KEY, kategoria TEXT, czy_zly INTEGER)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS biegi 
                    (id INTEGER PRIMARY KEY, data TEXT, dystans REAL, czas_min REAL, tempo_min_km REAL, notatka TEXT)''')
    
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM config_aktywnosci")
    if cur.fetchone()[0] == 0:
        dane = [("Pompki", "Treningi", 0), ("Podciągnięcia", "Treningi", 0), 
                ("Basen (długości)", "Treningi", 0), ("Bieganie (km)", "Treningi", 0), ("Bieganie (tempo)", "Treningi", 0),
                ("Kawa", "Używki", 1), ("Słodycze", "Używki", 1), ("Junk Food", "Używki", 1), ("Alkohol", "Używki", 1),
                ("Sauna (min)", "Regeneracja", 0), ("Suplementy", "Regeneracja", 0),
                ("5", "Baldy", 0), ("6A", "Baldy", 0), ("6A+", "Baldy", 0), ("6B", "Baldy", 0), ("6C", "Baldy", 0), ("7A", "Baldy", 0),
                ("5", "Liny", 0), ("6a", "Liny", 0), ("6a+", "Liny", 0), ("6b", "Liny", 0), ("6c", "Liny", 0), ("7a", "Liny", 0)]
        cur.executemany("INSERT OR IGNORE INTO config_aktywnosci VALUES (?, ?, ?)", dane)
    conn.commit()
    conn.close()

# --- UNDO (NOWOŚĆ) ---
def cofnij_ostatni_log():
    """Usuwa ostatnio dodany wpis z tabeli logi"""
    conn = polacz()
    # Pobierz ostatni wpis żeby wiedzieć co usuwamy (do komunikatu)
    ostatni = conn.execute("SELECT id, aktywnosc, ilosc FROM logi ORDER BY id DESC LIMIT 1").fetchone()
    
    msg = None
    if ostatni:
        conn.execute("DELETE FROM logi WHERE id = ?", (ostatni[0],))
        conn.commit()
        msg = f"{ostatni[1]} ({ostatni[2]})"
    
    conn.close()
    return msg # Zwraca nazwę usuniętej rzeczy lub None

# --- RESZTA FUNKCJI (BEZ ZMIAN) ---
def dodaj_bieg(dystans, czas_min, notatka="", data_biegu=None):
    if data_biegu is None: data_biegu = str(date.today())
    else: data_biegu = str(data_biegu)
    tempo = czas_min / dystans if dystans > 0 else 0
    conn = polacz()
    conn.execute("INSERT INTO biegi (data, dystans, czas_min, tempo_min_km, notatka) VALUES (?, ?, ?, ?, ?)", 
                 (data_biegu, dystans, czas_min, tempo, notatka))
    conn.execute("INSERT INTO logi (data, aktywnosc, ilosc) VALUES (?, ?, ?)", (data_biegu, "Bieganie (km)", dystans))
    conn.execute("INSERT INTO logi (data, aktywnosc, ilosc) VALUES (?, ?, ?)", (data_biegu, "Bieganie (tempo)", tempo))
    conn.commit()
    conn.close()

def aktualizuj_bieg(id_biegu, kolumna, nowa_wartosc):
    conn = polacz()
    conn.execute(f"UPDATE biegi SET {kolumna} = ? WHERE id = ?", (nowa_wartosc, id_biegu))
    if kolumna in ['dystans', 'czas_min']:
        conn.execute("UPDATE biegi SET tempo_min_km = czas_min / dystans WHERE id = ?", (id_biegu,))
    conn.commit()
    conn.close()

def usun_bieg(id_biegu):
    conn = polacz()
    conn.execute("DELETE FROM biegi WHERE id = ?", (id_biegu,))
    conn.commit()
    conn.close()

def pobierz_historie_biegow():
    conn = polacz()
    df = pd.read_sql_query("SELECT * FROM biegi ORDER BY data DESC, id DESC", conn)
    conn.close()
    return df

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
    placeholders = ','.join('?' for _ in klucze)
    query = f"SELECT SUM(wartosc) FROM cele WHERE aktywnosc = ? AND klucz_tygodnia IN ({placeholders})"
    wynik = conn.execute(query, [aktywnosc] + klucze).fetchone()[0]
    conn.close()
    return wynik if wynik else 0

def pobierz_konfiguracje():
    conn = polacz()
    df = pd.read_sql_query("SELECT * FROM config_aktywnosci", conn)
    conn.close()
    return df

def dodaj_nowa_aktywnosc(nazwa, kategoria, czy_zly):
    conn = polacz()
    try:
        conn.execute("INSERT INTO config_aktywnosci VALUES (?, ?, ?)", (nazwa, kategoria, 1 if czy_zly else 0))
        conn.commit()
        return True
    except: return False
    finally: conn.close()

def usun_aktywnosc(nazwa):
    conn = polacz()
    conn.execute("DELETE FROM config_aktywnosci WHERE nazwa = ?", (nazwa,))
    conn.commit()
    conn.close()

def dodaj_log(aktywnosc, ilosc):
    conn = polacz()
    conn.execute("INSERT INTO logi (data, aktywnosc, ilosc) VALUES (?, ?, ?)", (str(date.today()), aktywnosc, ilosc))
    conn.commit()
    conn.close()

def ustaw_cel(aktywnosc, wartosc):
    conn = polacz()
    conn.execute("INSERT OR REPLACE INTO cele VALUES (?, ?, ?)", (daj_klucz_tygodnia(), aktywnosc, wartosc))
    conn.commit()
    conn.close()

def pobierz_stan_tygodnia_dict():
    conn = polacz()
    start = daj_zakres_dat_sql("Ten Tydzień")
    res = conn.execute("SELECT aktywnosc, SUM(ilosc) FROM logi WHERE data >= ? GROUP BY aktywnosc", (start,)).fetchall()
    conn.close()
    return {r[0]: r[1] for r in res}

def pobierz_cele_biezace_dict():
    conn = polacz()
    res = conn.execute("SELECT aktywnosc, wartosc FROM cele WHERE klucz_tygodnia = ?", (daj_klucz_tygodnia(),)).fetchall()
    conn.close()
    return {r[0]: r[1] for r in res}

def pobierz_dane_wykres(lista, okres):
    import pandas as pd
    if not lista: return pd.DataFrame(columns=['data', 'aktywnosc', 'ilosc'])
    conn = polacz()
    start = daj_zakres_dat_sql(okres)
    ph = ','.join('?' for _ in lista)
    df = pd.read_sql_query(f"SELECT data, aktywnosc, ilosc FROM logi WHERE data >= ? AND aktywnosc IN ({ph})", conn, params=[start] + lista)
    conn.close()
    return df