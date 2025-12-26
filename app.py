import streamlit as st
import pandas as pd
import altair as alt
import database 
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

database.init_db()

def climbing_sort_key(val):
    order = ["3", "4", "5", "5+", "6a", "6a+", "6b", "6b+", "6c", "6c+", "7a", "7a+", "7b", "7b+", "7c", "7c+", "8a", "8a+", "8b", "8b+", "8c", "9a"]
    val_lower = str(val).lower()
    if val_lower in order: return order.index(val_lower)
    return 999

df_config = database.get_config()

def get_sorted_list(category):
    items = df_config[df_config['category'] == category]['name'].tolist()
    if category in ["Bouldering", "Sport Climbing", "Baldy", "Liny"]: return sorted(items, key=climbing_sort_key)
    return sorted(items)

AVAILABLE_CATS = df_config['category'].unique().tolist()
STRUCTURE = {k: get_sorted_list(k) for k in AVAILABLE_CATS}

BAD_HABITS = df_config[df_config['is_bad']==1]['name'].tolist()
AVG_METRICS = ["Running (pace)", "Bieganie (tempo)"]

with st.sidebar:
    st.title(f"Hi, {st.session_state['current_user'].upper()}! 👋")
    
    selected_page = st.radio(
        "Navigate:", 
        ["🏠 Command Center", "🏃 Running Log", "📅 Planner"],
        label_visibility="collapsed"
    )
    
    st.markdown("---")
    
    with st.expander("⚡ QUICK ADD", expanded=True):
        if not STRUCTURE:
            st.warning("No categories found.")
        else:
            cat = st.selectbox("Category", list(STRUCTURE.keys()))
            act = st.selectbox("Activity", STRUCTURE[cat])
            
            climbing_cats = ["Bouldering", "Sport Climbing", "Baldy", "Liny"]
            
            if cat in climbing_cats:
                if st.button("DONE (+1)", type="primary", width="stretch"):
                    database.add_log(act, 1.0)
                    st.toast(f"Saved: {act}")
            else:
                is_float = "km" in act.lower() or "pace" in act.lower() or "tempo" in act.lower()
                
                if is_float:
                    val_def = 5.0; step_val = 1.0; fmt = "%.2f"
                    amount = st.number_input("Value", value=val_def, step=step_val, format=fmt)
                else:
                    val_def = 1; step_val = 1; fmt = "%d"
                    amount = st.number_input("Value", value=int(val_def), step=int(step_val), format=fmt)
                
                if st.button("SAVE", type="primary", width="stretch"):
                    database.add_log(act, amount)
                    st.toast(f"Saved: {act}")
    
    st.markdown("---")
    if st.button("Logout", width="stretch"):
        st.session_state['logged_in'] = False
        st.session_state['current_user'] = ""
        st.rerun()

states = database.get_weekly_state_dict()
goals = database.get_current_goals_dict()

def render_altair_chart(activity_list, period, category):
    df = database.get_chart_data(activity_list, period)
    
    if df.empty:
        df_agg = pd.DataFrame(activity_list, columns=['aktywnosc']); df_agg['ilosc'] = 0
    else:
        df_agg = df.groupby("aktywnosc")['ilosc'].sum().reset_index()
    
    df_full = pd.merge(pd.DataFrame(activity_list, columns=['aktywnosc']), df_agg, on='aktywnosc', how='left').fillna(0)
    df_full['Goal_Hist'] = df_full['aktywnosc'].apply(lambda x: database.calc_historical_goal(x, period))
    
    df_full.loc[df_full['aktywnosc'].str.contains("pace|tempo", case=False, na=False), 'Goal_Hist'] = 0
    
    color_bar = "#4CAF50"
    if category in ["Bouldering", "Sport Climbing", "Baldy", "Liny"]: color_bar = "#FFC107"
    elif any(x in BAD_HABITS for x in activity_list): color_bar = "#FF5252"
    
    base = alt.Chart(df_full).encode(
        x=alt.X('aktywnosc', title=None, sort=activity_list if category in ["Bouldering", "Sport Climbing"] else None),
        tooltip=['aktywnosc', 'ilosc', 'Goal_Hist']
    )
    bars = base.mark_bar(color=color_bar, opacity=0.9).encode(y=alt.Y('ilosc', title='Value'))
    ticks = base.transform_filter(alt.datum.Goal_Hist > 0).mark_tick(color='white', thickness=2, size=30).encode(y='Goal_Hist')
    st.altair_chart((bars + ticks).properties(height=250), use_container_width=True)

def render_simple_section(title, category, is_bad_habit=False):
    st.subheader(title)
    items_list = STRUCTURE.get(category, [])
    if not items_list: st.caption("No activities."); return

    has_content = False
    for act in items_list:
        s = states.get(act, 0)
        c = goals.get(act, 0)
        if c == 0 and s == 0: continue
        has_content = True

        c1, c2, c3 = st.columns([2, 4, 2])
        c1.write(f"**{act}**")
        
        if act in AVG_METRICS:
            c2.info(f"Avg: {s:.2f}")
        else:
            proc = min(s/c if c>0 else 0, 1.0)
            if is_bad_habit and c>0 and s>c: c2.error("LIMIT")
            else: c2.progress(proc)
        
        with c3:
            label_btn = f"{int(s)} / {int(c)}"
            if act in AVG_METRICS: label_btn = f"{s:.2f}"
            key_pop = f"edit_{title}_{act}"
            
            with st.popover(label_btn, use_container_width=True, help="Edit value"):
                st.write(f"Correct: **{act}**")
                is_float = "km" in act.lower() or "pace" in act.lower() or "tempo" in act.lower()
                
                if is_float:
                    step = 0.5; fmt = "%.2f"; val = float(s)
                else:
                    step = 1; fmt = "%d"; val = int(s)
                
                new_value = st.number_input("State:", value=val, step=step, format=fmt, key=f"input_{key_pop}")
                
                if st.button("Confirm", key=f"btn_{key_pop}", width="stretch"):
                    delta = new_value - val
                    if delta != 0:
                        database.add_log(act, delta)
                        st.toast("Updated!")
                        st.rerun()

    if not has_content: st.caption("No data (0/0).")

    with st.expander(f"📈 Chart: {title}"):
        period = st.selectbox("Period", ["This Week", "This Month", "This Year"], key=f"o_{category}")
        render_altair_chart(items_list, period, category)

def handle_table_changes():
    if "editor_runs" not in st.session_state: return
    changes = st.session_state["editor_runs"]
    
    for idx in changes["deleted_rows"]:
        id_to_del = st.session_state["df_runs_snapshot"].iloc[idx]['id']
        database.delete_run(int(id_to_del))
        st.toast("🗑️ Run deleted!")

    for idx, row_changes in changes["edited_rows"].items():
        run_id = st.session_state["df_runs_snapshot"].iloc[idx]['id']
        for col_name, new_val in row_changes.items():
            database.update_run(int(run_id), col_name, new_val)
        st.toast("✏️ Updated!")

    for new_row in changes["added_rows"]:
        dist = new_row.get("distance", 0); t_min = new_row.get("time_min", 0)
        d = new_row.get("date", str(date.today())); note = new_row.get("note", "")
        if dist > 0 and t_min > 0:
            database.add_run(dist, t_min, note, d)
            st.toast("🏃 Run added!")

if selected_page == "🏠 Command Center":
    st.title("Command Center")
    view_options = ["All"] + list(STRUCTURE.keys())
    view = st.radio("Show:", view_options, horizontal=True)
    st.markdown("---")

    if view == "All":
        cats = list(STRUCTURE.keys())
        for i in range(0, len(cats), 3):
            cols = st.columns(3, gap="large")
            for j in range(3):
                if i + j < len(cats):
                    cat_name = cats[i + j]
                    is_bad = any(x in BAD_HABITS for x in STRUCTURE[cat_name])
                    with cols[j]: render_simple_section(cat_name, cat_name, is_bad_habit=is_bad)
            if i + 3 < len(cats): st.markdown("<br>", unsafe_allow_html=True)
    else:
        is_bad = any(x in BAD_HABITS for x in STRUCTURE[view])
        render_simple_section(view, view, is_bad_habit=is_bad)

elif selected_page == "🏃 Running Log":
    st.title("🏃 Running Log")
    col_add, col_list = st.columns([1, 2], gap="large")
    with col_add:
        st.success("Add New Run")
        with st.form("run_form"):
            d = st.date_input("Date", value=date.today())
            km = st.number_input("Distance (km)", value=5.0, step=1.0)
            t = st.number_input("Time (min)", value=30.0, step=1.0)
            n = st.text_input("Note")
            if st.form_submit_button("SAVE RUN", width="stretch"):
                database.add_run(km, t, n, d); st.rerun()
    with col_list:
        st.subheader("History")
        df_runs = database.get_run_history()
        if not df_runs.empty and 'date' in df_runs.columns: df_runs['date'] = pd.to_datetime(df_runs['date']).dt.date
        st.session_state["df_runs_snapshot"] = df_runs
        
        if not df_runs.empty:
            scatter = alt.Chart(df_runs).mark_circle(size=100).encode(
                x='date', y='pace', color='distance', tooltip=['date', 'note']
            ).interactive()
            st.altair_chart(scatter, use_container_width=True)
            
            edit_mode = st.toggle("✏️ Enable Editing", value=False)
            st.data_editor(
                df_runs, key="editor_runs", on_change=handle_table_changes,
                num_rows="dynamic" if edit_mode else "fixed", hide_index=True, use_container_width=True,
                column_config={
                    "id": st.column_config.NumberColumn(disabled=True),
                    "pace": st.column_config.NumberColumn("Pace", format="%.2f", disabled=True),
                    "date": st.column_config.DateColumn("Date", disabled=not edit_mode),
                    "distance": st.column_config.NumberColumn("km", format="%.2f", step=0.1, disabled=not edit_mode),
                    "time_min": st.column_config.NumberColumn("min", format="%d", step=1, disabled=not edit_mode),
                    "note": st.column_config.TextColumn("Note", disabled=not edit_mode)
                }
            )
        else: st.info("No runs found.")

elif selected_page == "📅 Planner":
    st.title("📅 Planner")
    
    df_plan = database.get_full_planner()
    st.session_state["df_plan_snapshot"] = df_plan

    if "temp_categories" not in st.session_state: st.session_state.temp_categories = []
    
    db_cats = df_plan['Category'].unique().tolist()
    all_cats_for_dropdown = sorted(list(set(db_cats + st.session_state.temp_categories)))

    col_tools, col_filter = st.columns([1, 2])
    with col_tools:
        with st.popover("⚙️ Manage Categories", use_container_width=True):
            tab1, tab2, tab3 = st.tabs(["Add", "Rename", "Cleanup"])
            
            with tab1:
                new_cat_input = st.text_input("New Category Name")
                if st.button("Add to List", key="btn_add_cat"):
                    if new_cat_input and new_cat_input not in all_cats_for_dropdown:
                        st.session_state.temp_categories.append(new_cat_input)
                        st.rerun()
            
            with tab2:
                cat_to_rename = st.selectbox("Select Category to Rename", db_cats)
                new_name_rename = st.text_input("New Name")
                if st.button("Rename Category", key="btn_rename_cat"):
                    if new_name_rename and cat_to_rename:
                        database.rename_category_in_db(cat_to_rename, new_name_rename)
                        st.success("Renamed!")
                        time.sleep(1)
                        st.rerun()

            with tab3:
                st.caption("Remove unused categories from the session list.")
                cat_to_del = st.selectbox("Select Temp Category", st.session_state.temp_categories)
                if st.button("Remove from List", key="btn_del_cat"):
                    if cat_to_del in st.session_state.temp_categories:
                        st.session_state.temp_categories.remove(cat_to_del)
                        st.rerun()

    with col_filter:
        cat_filter = st.selectbox("Filter:", ["All Categories"] + all_cats_for_dropdown)

    if cat_filter != "All Categories":
        df_display = df_plan[df_plan['Category'] == cat_filter]
    else:
        df_display = df_plan

    st.info("💡 You can add new rows below. Use 'Manage Categories' to add/edit categories.")
    
    edited = st.data_editor(
        df_display,
        key="editor_planner",
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Activity": st.column_config.TextColumn(
                required=True, 
                width="large",
                help="Unique name (e.g. 6b+, Running)"
            ),
            "Category": st.column_config.SelectboxColumn(
                width="medium",
                options=all_cats_for_dropdown, 
                required=True
            ),
            "Is Bad Habit": st.column_config.CheckboxColumn(
                label="Bad?", 
                width="small"
            ),
            "Weekly Goal": st.column_config.NumberColumn(
                min_value=0, 
                step=1,
                width="small"
            )
        }
    )

    if st.button("SAVE CHANGES", type="primary", width="stretch"):
        if "editor_planner" in st.session_state:
            changes = st.session_state["editor_planner"]
            if changes["edited_rows"] or changes["deleted_rows"] or changes["added_rows"]:
                database.update_planner_batch(changes, st.session_state["df_plan_snapshot"])
                st.success("Changes saved!")
                time.sleep(1)
                st.rerun()
            else:
                st.info("No changes detected.")