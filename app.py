import streamlit as st
import pandas as pd
import altair as alt
import baza 
from datetime import date
import time

st.set_page_config(page_title="Panel Treningowy PRO", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    .stProgress > div > div > div > div { background-color: #4CAF50; }
    div[data-testid="column"] { 
        background: rgba(255, 255, 255, 0.02); 
        padding: 20px; 
        border-radius: 12px; 
        border: 1px solid rgba(255,255,255,0.05); 
        min-height: 100%;
    }
    h3 { 
        border-bottom: 1px solid rgba(255,255,255,0.1); 
        padding-bottom: 10px; margin-top: 0px; margin-bottom: 20px;
        font-size: 1.2rem; letter-spacing: 1px; text-transform: uppercase; color: #ddd;
    }
    .stRadio > div { gap: 10px; }
    button[kind="secondary"] { font-weight: bold; }
</style>
""", unsafe_allow_html=True)


if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

def check_login():
    user = st.session_state['login_user']
    password = st.session_state['login_pass']

    
    try:
        correct_pass = st.secrets["users"][user]
        if password == correct_pass:
            st.session_state['logged_in'] = True
            # Przypisujemy odpowiednią bazę danych
            st.session_state['db_url'] = st.secrets["db_urls"][user]
            st.success("Zalogowano! Ładowanie...")
            time.sleep(1)
            st.rerun()
        else:
            st.error("Błędne hasło!")
    except KeyError:
        st.error(f"Nieznany użytkownik w konfiguracji: {user}")

if not st.session_state['logged_in']:
    st.title("🔒 Panel Treningowy - Logowanie")
    
    users_list = ["user1", "user2", "user3"]
    
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.selectbox("Wybierz profil:", users_list, key="login_user")
        st.text_input("Hasło:", type="password", key="login_pass")
        st.button("ZALOGUJ", on_click=check_login, type="primary", width="stretch")
    
    st.stop()


baza.inicjalizuj_baze()

def wspin_sort_key(val):
    order = ["3", "4", "5", "5+", "6a", "6a+", "6b", "6b+", "6c", "6c+", "7a", "7a+", "7b", "7b+", "7c", "7c+", "8a", "8a+", "8b", "8b+", "8c", "9a"]
    val_lower = str(val).lower()
    if val_lower in order: return order.index(val_lower)
    return 999

df_conf = baza.pobierz_konfiguracje()

def get_sorted_list(kategoria):
    items = df_conf[df_conf['kategoria'] == kategoria]['nazwa'].tolist()
    if kategoria in ["Baldy", "Liny"]: return sorted(items, key=wspin_sort_key)
    return sorted(items)

DOSTEPNE_KAT = df_conf['kategoria'].unique().tolist()
STRUKTURA = {k: get_sorted_list(k) for k in DOSTEPNE_KAT}

ZLE_NAWYKI = df_conf[df_conf['czy_zly']==1]['nazwa'].tolist()
METRYKI_SREDNIE = ["Bieganie (tempo)"]

with st.sidebar:
    st.title(f"Witaj, {st.session_state['login_user'].upper()}! 👋")
    
    wybrana_strona = st.radio(
        "Przejdź do:", 
        ["🏠 Centrum Dowodzenia", "🏃 Dziennik Biegowy", "📅 Planer Celów", "⚙️ Konfiguracja"],
        label_visibility="collapsed"
    )
    
    st.markdown("---")
    
    with st.expander("⚡ SZYBKI ZAPIS", expanded=True):
        if not STRUKTURA:
            st.warning("Brak kategorii.")
        else:
            kat = st.selectbox("Kategoria", list(STRUKTURA.keys()))
            akt = st.selectbox("Co?", STRUKTURA[kat])
            
            if kat in ["Baldy", "Liny"]:
                if st.button("ZALICZONO (+1)", type="primary", width="stretch"):
                    baza.dodaj_log(akt, 1.0)
                    st.toast(f"Zapisano: {akt}")
            else:
                is_float = "km" in akt.lower() or "tempo" in akt.lower() or "sauna" in akt.lower()
                
                if is_float:
                    val_def = 5.0; step_val = 1.0; fmt = "%.2f"
                    ilosc = st.number_input("Ilość", value=val_def, step=step_val, format=fmt)
                else:
                    val_def = 1; step_val = 1; fmt = "%d"
                    ilosc = st.number_input("Ilość", value=int(val_def), step=int(step_val), format=fmt)
                
                if st.button("ZAPISZ", type="primary", width="stretch"):
                    baza.dodaj_log(akt, ilosc)
                    st.toast(f"Zapisano: {akt}")
    
    st.markdown("---")
    if st.button("Wyloguj", width="stretch"):
        st.session_state['logged_in'] = False
        st.rerun()

stany = baza.pobierz_stan_tygodnia_dict()
cele = baza.pobierz_cele_biezace_dict()

def render_wykres_altair(lista_aktywnosci, okres, kategoria):
    df = baza.pobierz_dane_wykres(lista_aktywnosci, okres)
    
    if df.empty:
        df_agg = pd.DataFrame(lista_aktywnosci, columns=['aktywnosc']); df_agg['ilosc'] = 0
    else:
        if kategoria == "Treningi" and any("tempo" in x for x in lista_aktywnosci):
             df_agg = df.groupby("aktywnosc")['ilosc'].sum().reset_index()
        else:
             df_agg = df.groupby("aktywnosc")['ilosc'].sum().reset_index()
    
    df_full = pd.merge(pd.DataFrame(lista_aktywnosci, columns=['aktywnosc']), df_agg, on='aktywnosc', how='left').fillna(0)
    df_full['Cel_Hist'] = df_full['aktywnosc'].apply(lambda x: baza.oblicz_cel_historyczny(x, okres))
    df_full.loc[df_full['aktywnosc'].str.contains("tempo", case=False, na=False), 'Cel_Hist'] = 0
    
    color_bar = "#4CAF50"
    if kategoria in ["Baldy", "Liny"]: color_bar = "#FFC107"
    elif any(x in ZLE_NAWYKI for x in lista_aktywnosci): color_bar = "#FF5252"
    
    base = alt.Chart(df_full).encode(
        x=alt.X('aktywnosc', title=None, sort=lista_aktywnosci if kategoria in ["Baldy", "Liny"] else None),
        tooltip=['aktywnosc', 'ilosc', 'Cel_Hist']
    )
    bars = base.mark_bar(color=color_bar, opacity=0.9).encode(y=alt.Y('ilosc', title='Wartość'))
    ticks = base.transform_filter(alt.datum.Cel_Hist > 0).mark_tick(color='white', thickness=2, size=30).encode(y='Cel_Hist')
    st.altair_chart((bars + ticks).properties(height=250), use_container_width=True)

def render_sekcja_prosta(tytul, kategoria, czy_zly=False):
    st.subheader(tytul)
    lista = STRUKTURA.get(kategoria, [])
    if not lista: st.caption("Brak aktywności."); return

    has_content = False
    for akt in lista:
        s = stany.get(akt, 0)
        c = cele.get(akt, 0)
        if c == 0 and s == 0: continue
        has_content = True

        c1, c2, c3 = st.columns([2, 4, 2])
        c1.write(f"**{akt}**")
        
        if akt in METRYKI_SREDNIE:
            c2.info(f"Śr: {s:.2f}")
        else:
            proc = min(s/c if c>0 else 0, 1.0)
            if czy_zly and c>0 and s>c: c2.error("LIMIT")
            else: c2.progress(proc)
        
        with c3:
            label_btn = f"{int(s)} / {int(c)}"
            if akt in METRYKI_SREDNIE: label_btn = f"{s:.2f}"
            key_pop = f"edit_{tytul}_{akt}"
            
            with st.popover(label_btn, use_container_width=True, help="Edytuj wynik"):
                st.write(f"Korekta: **{akt}**")
                is_float = "km" in akt.lower() or "tempo" in akt.lower()
                
                if is_float:
                    step = 0.5; fmt = "%.2f"; val = float(s)
                else:
                    step = 1; fmt = "%d"; val = int(s)
                
                nowa_wartosc = st.number_input("Stan:", value=val, step=step, format=fmt, key=f"input_{key_pop}")
                
                if st.button("Zatwierdź", key=f"btn_{key_pop}", width="stretch"):
                    delta = nowa_wartosc - val
                    if delta != 0:
                        baza.dodaj_log(akt, delta)
                        st.toast("Zaktualizowano!")
                        st.rerun()

    if not has_content: st.caption("Brak danych (0/0).")

    with st.expander(f"📈 Wykres {tytul}"):
        okres = st.selectbox("Okres", ["Ten Tydzień", "Ten Miesiąc", "Ten Rok"], key=f"o_{kategoria}")
        render_wykres_altair(lista, okres, kategoria)


def obsluga_zmian_tabeli():
    if "editor_biegi" not in st.session_state: return
    changes = st.session_state["editor_biegi"]
    
    for idx in changes["deleted_rows"]:
        id_do_usuniecia = st.session_state["df_biegi_snapshot"].iloc[idx]['id']
        baza.usun_bieg(int(id_do_usuniecia))
        st.toast("🗑️ Bieg usunięty!")

    for idx, row_changes in changes["edited_rows"].items():
        id_biegu = st.session_state["df_biegi_snapshot"].iloc[idx]['id']
        for col_name, new_val in row_changes.items():
            baza.aktualizuj_bieg(int(id_biegu), col_name, new_val)
        st.toast("✏️ Zaktualizowano wpis!")

    for new_row in changes["added_rows"]:
        dist = new_row.get("dystans", 0); czas = new_row.get("czas_min", 0)
        data = new_row.get("data", str(date.today())); notatka = new_row.get("notatka", "")
        if dist > 0 and czas > 0:
            baza.dodaj_bieg(dist, czas, notatka, data)
            st.toast("🏃 Dodano bieg!")


if wybrana_strona == "🏠 Centrum Dowodzenia":
    st.title("Centrum Dowodzenia")
    opcje_widoku = ["Wszystko"] + list(STRUKTURA.keys())
    widok = st.radio("Pokaż:", opcje_widoku, horizontal=True)
    st.markdown("---")

    if widok == "Wszystko":
        kategorie = list(STRUKTURA.keys())
        for i in range(0, len(kategorie), 3):
            cols = st.columns(3, gap="large")
            for j in range(3):
                if i + j < len(kategorie):
                    kat_name = kategorie[i + j]
                    is_bad = any(x in ZLE_NAWYKI for x in STRUKTURA[kat_name])
                    with cols[j]: render_sekcja_prosta(kat_name, kat_name, czy_zly=is_bad)
            if i + 3 < len(kategorie): st.markdown("<br>", unsafe_allow_html=True)
    else:
        is_bad = any(x in ZLE_NAWYKI for x in STRUKTURA[widok])
        render_sekcja_prosta(widok, widok, czy_zly=is_bad)

elif wybrana_strona == "🏃 Dziennik Biegowy":
    st.title("🏃 Dziennik Biegowy")
    col_add, col_list = st.columns([1, 2], gap="large")
    with col_add:
        st.success("Dodaj nowy bieg")
        with st.form("bieg"):
            d = st.date_input("Data", value=date.today())
            km = st.number_input("Dystans (km)", value=5.0, step=1.0)
            t = st.number_input("Czas (min)", value=30.0, step=1.0)
            n = st.text_input("Notatka")
            if st.form_submit_button("ZAPISZ BIEG", width="stretch"):
                baza.dodaj_bieg(km, t, n, d); st.rerun()
    with col_list:
        st.subheader("Historia")
        df_b = baza.pobierz_historie_biegow()
        if not df_b.empty and 'data' in df_b.columns: df_b['data'] = pd.to_datetime(df_b['data']).dt.date
        st.session_state["df_biegi_snapshot"] = df_b
        if not df_b.empty:
            scatter = alt.Chart(df_b).mark_circle(size=100).encode(
                x='data', y='tempo_min_km', color='dystans', tooltip=['data', 'notatka']
            ).interactive()
            st.altair_chart(scatter, use_container_width=True)
            tryb_edycji = st.toggle("✏️ Odblokuj edycję tabeli", value=False)
            st.data_editor(
                df_b, key="editor_biegi", on_change=obsluga_zmian_tabeli,
                num_rows="dynamic" if tryb_edycji else "fixed", hide_index=True, use_container_width=True,
                column_config={
                    "id": st.column_config.NumberColumn(disabled=True),
                    "tempo_min_km": st.column_config.NumberColumn("Tempo", format="%.2f", disabled=True),
                    "data": st.column_config.DateColumn("Data", disabled=not tryb_edycji),
                    "dystans": st.column_config.NumberColumn("km", format="%.2f", step=0.1, disabled=not tryb_edycji),
                    "czas_min": st.column_config.NumberColumn("min", format="%d", step=1, disabled=not tryb_edycji),
                    "notatka": st.column_config.TextColumn("Notatka", disabled=not tryb_edycji)
                }
            )
            if not tryb_edycji: st.caption("🔒 Tabela zablokowana. Użyj przełącznika powyżej, aby edytować.")
            else: st.warning("⚠️ Tryb edycji! Zmiany w tabeli są zapisywane automatycznie.")
        else: st.info("Brak wpisów.")

elif wybrana_strona == "📅 Planer Celów":
    st.title("📅 Planowanie Tygodnia")
    all_items = []
    for k, v in STRUKTURA.items():
        for i in v: all_items.append({"Kategoria": k, "Aktywność": i, "Cel": cele.get(i, 0)})
    df_plan = pd.DataFrame(all_items)
    edited = st.data_editor(df_plan, height=600, use_container_width=True, hide_index=True,
        column_config={
            "Kategoria": st.column_config.TextColumn(disabled=True),
            "Aktywność": st.column_config.TextColumn(disabled=True),
            "Cel": st.column_config.NumberColumn(min_value=0)
        }
    )
    if st.button("ZAPISZ CELE TYGODNIOWE", type="primary", width="stretch"):
        for i, row in edited.iterrows(): baza.ustaw_cel(row['Aktywność'], row['Cel'])
        st.success("Zapisano!"); st.rerun()

elif wybrana_strona == "⚙️ Konfiguracja":
    st.title("⚙️ Konfiguracja")
    c_add, c_del = st.columns(2, gap="large")
    with c_add:
        st.subheader("➕ Dodaj")
        new_name = st.text_input("Nazwa")
        kat_options = list(STRUKTURA.keys()) + ["➕ Nowa Kategoria..."]
        cat_sel = st.selectbox("Kategoria", kat_options)
        final_cat = cat_sel if cat_sel != "➕ Nowa Kategoria..." else st.text_input("Wpisz nazwę kategorii")
        is_bad = st.checkbox("Zły nawyk?", help="Zaznacz, jeśli to używka")
        if st.button("DODAJ", type="primary", width="stretch"):
            if new_name and final_cat:
                baza.dodaj_nowa_aktywnosc(new_name, final_cat, is_bad); st.success(f"Dodano: {new_name}"); st.rerun()
    with c_del:
        st.subheader("🗑️ Usuń")
        all_options = []
        for v in STRUKTURA.values(): all_options.extend(v)
        if all_options:
            to_remove = st.selectbox("Wybierz element", all_options)
            if st.button("USUŃ", width="stretch"): baza.usun_aktywnosc(to_remove); st.rerun()