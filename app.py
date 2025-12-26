import streamlit as st
import pandas as pd
import altair as alt
import baza 
from datetime import date
import time

st.set_page_config(page_title="Training Panel PRO", layout="wide", initial_sidebar_state="expanded")

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
if 'current_user' not in st.session_state:
    st.session_state['current_user'] = ""
if 'db_url' not in st.session_state:
    st.session_state['db_url'] = ""

if not st.session_state['logged_in']:
    st.title("🔒 Training Panel PRO - Login")
    
    users_list = ["user1", "user2", "user3"] 
    
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        selected_user = st.selectbox("Select Profile:", users_list)
        input_password = st.text_input("Password:", type="password")
        
        if st.button("LOGIN", type="primary", width="stretch"):
            try:
                correct_pass = st.secrets["users"][selected_user]
                
                if input_password == correct_pass:
                    st.session_state['logged_in'] = True
                    st.session_state['current_user'] = selected_user
                    st.session_state['db_url'] = st.secrets["db_urls"][selected_user]
                    
                    st.success("Logged in! Loading...")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("Invalid password!")
            except KeyError:
                st.error(f"Config Error: User '{selected_user}' not found in secrets.toml")
            except Exception as e:
                st.error(f"Unexpected error: {e}")
    
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
    if kategoria in ["Bouldering", "Sport Climbing", "Baldy", "Liny"]: return sorted(items, key=wspin_sort_key)
    return sorted(items)

DOSTEPNE_KAT = df_conf['kategoria'].unique().tolist()
STRUKTURA = {k: get_sorted_list(k) for k in DOSTEPNE_KAT}

ZLE_NAWYKI = df_conf[df_conf['czy_zly']==1]['nazwa'].tolist()
METRYKI_SREDNIE = ["Running (pace)", "Bieganie (tempo)"]

with st.sidebar:
    st.title(f"Hi, {st.session_state['current_user'].upper()}! 👋")
    
    wybrana_strona = st.radio(
        "Navigate:", 
        ["🏠 Command Center", "🏃 Running Log", "📅 Goal Planner & Manager"],
        label_visibility="collapsed"
    )
    
    st.markdown("---")
    
    with st.expander("⚡ QUICK ADD", expanded=True):
        if not STRUKTURA:
            st.warning("No categories found.")
        else:
            kat = st.selectbox("Category", list(STRUKTURA.keys()))
            akt = st.selectbox("Activity", STRUKTURA[kat])
            
            climbing_cats = ["Bouldering", "Sport Climbing", "Baldy", "Liny"]
            
            if kat in climbing_cats:
                if st.button("DONE (+1)", type="primary", width="stretch"):
                    baza.dodaj_log(akt, 1.0)
                    st.toast(f"Saved: {akt}")
            else:
                is_float = "km" in akt.lower() or "pace" in akt.lower() or "tempo" in akt.lower()
                
                if is_float:
                    val_def = 5.0; step_val = 1.0; fmt = "%.2f"
                    ilosc = st.number_input("Value", value=val_def, step=step_val, format=fmt)
                else:
                    val_def = 1; step_val = 1; fmt = "%d"
                    ilosc = st.number_input("Value", value=int(val_def), step=int(step_val), format=fmt)
                
                if st.button("SAVE", type="primary", width="stretch"):
                    baza.dodaj_log(akt, ilosc)
                    st.toast(f"Saved: {akt}")
    
    st.markdown("---")
    if st.button("Logout", width="stretch"):
        st.session_state['logged_in'] = False
        st.session_state['current_user'] = ""
        st.rerun()

stany = baza.pobierz_stan_tygodnia_dict()
cele = baza.pobierz_cele_biezace_dict()

def render_wykres_altair(lista_aktywnosci, okres, kategoria):
    df = baza.pobierz_dane_wykres(lista_aktywnosci, okres)
    
    if df.empty:
        df_agg = pd.DataFrame(lista_aktywnosci, columns=['aktywnosc']); df_agg['ilosc'] = 0
    else:
        df_agg = df.groupby("aktywnosc")['ilosc'].sum().reset_index()
    
    df_full = pd.merge(pd.DataFrame(lista_aktywnosci, columns=['aktywnosc']), df_agg, on='aktywnosc', how='left').fillna(0)
    df_full['Cel_Hist'] = df_full['aktywnosc'].apply(lambda x: baza.oblicz_cel_historyczny(x, okres))
    
    df_full.loc[df_full['aktywnosc'].str.contains("pace|tempo", case=False, na=False), 'Cel_Hist'] = 0
    
    color_bar = "#4CAF50"
    if kategoria in ["Bouldering", "Sport Climbing", "Baldy", "Liny"]: color_bar = "#FFC107"
    elif any(x in ZLE_NAWYKI for x in lista_aktywnosci): color_bar = "#FF5252"
    
    base = alt.Chart(df_full).encode(
        x=alt.X('aktywnosc', title=None, sort=lista_aktywnosci if kategoria in ["Bouldering", "Sport Climbing"] else None),
        tooltip=['aktywnosc', 'ilosc', 'Cel_Hist']
    )
    bars = base.mark_bar(color=color_bar, opacity=0.9).encode(y=alt.Y('ilosc', title='Value'))
    ticks = base.transform_filter(alt.datum.Cel_Hist > 0).mark_tick(color='white', thickness=2, size=30).encode(y='Cel_Hist')
    st.altair_chart((bars + ticks).properties(height=250), use_container_width=True)

def render_sekcja_prosta(tytul, kategoria, czy_zly=False):
    st.subheader(tytul)
    lista = STRUKTURA.get(kategoria, [])
    if not lista: st.caption("No activities."); return

    has_content = False
    for akt in lista:
        s = stany.get(akt, 0)
        c = cele.get(akt, 0)
        if c == 0 and s == 0: continue
        has_content = True

        c1, c2, c3 = st.columns([2, 4, 2])
        c1.write(f"**{akt}**")
        
        if akt in METRYKI_SREDNIE:
            c2.info(f"Avg: {s:.2f}")
        else:
            proc = min(s/c if c>0 else 0, 1.0)
            if czy_zly and c>0 and s>c: c2.error("LIMIT")
            else: c2.progress(proc)
        
        with c3:
            label_btn = f"{int(s)} / {int(c)}"
            if akt in METRYKI_SREDNIE: label_btn = f"{s:.2f}"
            key_pop = f"edit_{tytul}_{akt}"
            
            with st.popover(label_btn, use_container_width=True, help="Edit value"):
                st.write(f"Correct: **{akt}**")
                is_float = "km" in akt.lower() or "pace" in akt.lower() or "tempo" in akt.lower()
                
                if is_float:
                    step = 0.5; fmt = "%.2f"; val = float(s)
                else:
                    step = 1; fmt = "%d"; val = int(s)
                
                nowa_wartosc = st.number_input("State:", value=val, step=step, format=fmt, key=f"input_{key_pop}")
                
                if st.button("Confirm", key=f"btn_{key_pop}", width="stretch"):
                    delta = nowa_wartosc - val
                    if delta != 0:
                        baza.dodaj_log(akt, delta)
                        st.toast("Updated!")
                        st.rerun()

    if not has_content: st.caption("No data (0/0).")

    with st.expander(f"📈 Chart: {tytul}"):
        okres = st.selectbox("Period", ["This Week", "This Month", "This Year"], key=f"o_{kategoria}")
        render_wykres_altair(lista, okres, kategoria)

def obsluga_zmian_tabeli():
    if "editor_biegi" not in st.session_state: return
    changes = st.session_state["editor_biegi"]
    
    for idx in changes["deleted_rows"]:
        id_do_usuniecia = st.session_state["df_biegi_snapshot"].iloc[idx]['id']
        baza.usun_bieg(int(id_do_usuniecia))
        st.toast("🗑️ Run deleted!")

    for idx, row_changes in changes["edited_rows"].items():
        id_biegu = st.session_state["df_biegi_snapshot"].iloc[idx]['id']
        for col_name, new_val in row_changes.items():
            baza.aktualizuj_bieg(int(id_biegu), col_name, new_val)
        st.toast("✏️ Updated!")

    for new_row in changes["added_rows"]:
        dist = new_row.get("dystans", 0); czas = new_row.get("czas_min", 0)
        data = new_row.get("data", str(date.today())); notatka = new_row.get("notatka", "")
        if dist > 0 and czas > 0:
            baza.dodaj_bieg(dist, czas, notatka, data)
            st.toast("🏃 Run added!")

if wybrana_strona == "🏠 Command Center":
    st.title("Command Center")
    opcje_widoku = ["All"] + list(STRUKTURA.keys())
    widok = st.radio("Show:", opcje_widoku, horizontal=True)
    st.markdown("---")

    if widok == "All":
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

elif wybrana_strona == "🏃 Running Log":
    st.title("🏃 Running Log")
    col_add, col_list = st.columns([1, 2], gap="large")
    with col_add:
        st.success("Add New Run")
        with st.form("bieg"):
            d = st.date_input("Date", value=date.today())
            km = st.number_input("Distance (km)", value=5.0, step=1.0)
            t = st.number_input("Time (min)", value=30.0, step=1.0)
            n = st.text_input("Note")
            if st.form_submit_button("SAVE RUN", width="stretch"):
                baza.dodaj_bieg(km, t, n, d); st.rerun()
    with col_list:
        st.subheader("History")
        df_b = baza.pobierz_historie_biegow()
        if not df_b.empty and 'data' in df_b.columns: df_b['data'] = pd.to_datetime(df_b['data']).dt.date
        st.session_state["df_biegi_snapshot"] = df_b
        if not df_b.empty:
            scatter = alt.Chart(df_b).mark_circle(size=100).encode(
                x='data', y='tempo_min_km', color='dystans', tooltip=['data', 'notatka']
            ).interactive()
            st.altair_chart(scatter, use_container_width=True)
            
            tryb_edycji = st.toggle("✏️ Enable Editing", value=False)
            st.data_editor(
                df_b, key="editor_biegi", on_change=obsluga_zmian_tabeli,
                num_rows="dynamic" if tryb_edycji else "fixed", hide_index=True, use_container_width=True,
                column_config={
                    "id": st.column_config.NumberColumn(disabled=True),
                    "tempo_min_km": st.column_config.NumberColumn("Pace", format="%.2f", disabled=True),
                    "data": st.column_config.DateColumn("Date", disabled=not tryb_edycji),
                    "dystans": st.column_config.NumberColumn("km", format="%.2f", step=0.1, disabled=not tryb_edycji),
                    "czas_min": st.column_config.NumberColumn("min", format="%d", step=1, disabled=not tryb_edycji),
                    "notatka": st.column_config.TextColumn("Note", disabled=not tryb_edycji)
                }
            )
        else: st.info("No runs found.")

elif wybrana_strona == "📅 Goal Planner & Manager":
    st.title("📅 Goal Planner & Manager")
    
    with st.expander("➕ Add New Activity", expanded=False):
        c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
        new_name = c1.text_input("Name (e.g. Yoga)")
        new_cat = c2.text_input("Category (e.g. Recovery)")
        new_bad = c3.checkbox("Bad Habit?")
        if c4.button("ADD", type="primary", width="stretch"):
            if new_name and new_cat:
                if baza.dodaj_nowa_aktywnosc(new_name, new_cat, new_bad):
                    st.success(f"Added: {new_name}")
                    st.rerun()
                else: st.error("Error or duplicate.")
            else: st.warning("Name and Category required.")

    st.markdown("---")

    df_plan = baza.pobierz_pelny_planer()
    st.session_state["df_plan_snapshot"] = df_plan

    all_cats = ["All Categories"] + sorted(df_plan['Category'].unique().tolist())
    cat_filter = st.selectbox("Filter:", all_cats)

    if cat_filter != "All Categories":
        df_display = df_plan[df_plan['Category'] == cat_filter]
    else:
        df_display = df_plan

    st.info("💡 Edit Categories, Bad Habit status, or Weekly Goals here. Use 'DEL' key to remove rows.")
    edited = st.data_editor(
        df_display,
        key="editor_planer",
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Activity": st.column_config.TextColumn(disabled=True, help="To rename, delete and add new."),
            "Category": st.column_config.TextColumn(),
            "Is Bad Habit": st.column_config.CheckboxColumn(),
            "Weekly Goal": st.column_config.NumberColumn(min_value=0, step=1)
        }
    )

    if st.button("SAVE CHANGES", type="primary", width="stretch"):
        if "editor_planer" in st.session_state:
            changes = st.session_state["editor_planer"]
            if changes["edited_rows"] or changes["deleted_rows"] or changes["added_rows"]:
                if changes["added_rows"]:
                    st.warning("Please use the 'Add New Activity' form above to add items.")
                
                baza.aktualizuj_planer_batch(changes, st.session_state["df_plan_snapshot"])
                st.success("Changes saved!")
                time.sleep(1)
                st.rerun()
            else:
                st.info("No changes detected.")