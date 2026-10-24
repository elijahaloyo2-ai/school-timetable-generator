import streamlit as st
import pandas as pd
from supabase import create_client, Client
import random
import io

# Page Configuration
st.set_page_config(page_title="KEA Comprehensive School Timetable System", layout="wide")
st.title("KEA Comprehensive School - Automated Timetable System")

SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")

@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

# --- PREDEFINED CBC LEARNING AREAS & SUBJECT CODES ---
CBC_SUBJECTS = {
    "MATHS": {"name": "Mathematics", "double": False},
    "ENG": {"name": "English", "double": False},
    "KISW": {"name": "Kiswahili", "double": False},
    "ENV": {"name": "Environmental", "double": False},
    "C.R.E": {"name": "Christian Religious Education", "double": False},
    "C/A": {"name": "Creative Arts", "double": False},
    "AGR/NUT": {"name": "Agriculture and Nutrition", "double": False},
    "SCI/TECH": {"name": "Science and Technology", "double": False},
    "SOC": {"name": "Social Studies", "double": False},
    "AGRIC": {"name": "Agriculture", "double": True},       # Junior double allowed
    "PRE": {"name": "Pretechnical Studies", "double": True},  # Junior double allowed
    "INT SCI": {"name": "Integrated Science", "double": True},# Junior double allowed
    "C.A.S": {"name": "Creative Arts and Sports", "double": True} # Junior double allowed
}

DAYS_ORDER = ["MON", "TUE", "WED", "THUR", "FRI"]

# Navigation
menu = st.sidebar.selectbox(
    "Navigation", 
    ["1. Setup Teachers & Classes", "2. Assign Teaching Areas", "3. Data Management", "4. Generate Timetable", "5. View & Export Timetables"]
)

# ---------------------------------------------------------
# MODULE 1: SETUP TEACHERS & CLASSES
# ---------------------------------------------------------
if menu == "1. Setup Teachers & Classes":
    st.header("Step 1: Register Teachers & School Classes")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Add Teacher")
        t_code = st.text_input("Teacher Code (e.g., Code 01, T01)")
        t_name = st.text_input("Teacher Name")
        t_max = st.number_input("Max Teaching Periods / Day", min_value=1, max_value=8, value=6)
        if st.button("Save Teacher"):
            if t_name and t_code:
                supabase.table("teachers").insert({"code": t_code, "name": t_name, "max_periods_per_day": t_max}).execute()
                st.success(f"Added Teacher: {t_name} ({t_code})")
                st.rerun()
            else:
                st.error("Please provide both Teacher Code and Name.")

    with col2:
        st.subheader("Add Class / Stream")
        c_name = st.text_input("Class Name (e.g., Grade 1, Grade 5, Grade 8)")
        c_category = st.selectbox("Section / Category", ["Lower Primary (Grade 1-3)", "Upper Primary (Grade 4-6)", "Junior School (Grade 7-9)"])
        
        if st.button("Save Class"):
            if c_name:
                supabase.table("classes").insert({"name": c_name.upper(), "category": c_category}).execute()
                st.success(f"Added Class: {c_name.upper()} ({c_category})")
                st.rerun()

# ---------------------------------------------------------
# MODULE 2: ASSIGN TEACHING AREAS (NO MANUAL SUBJECT CREATION)
# ---------------------------------------------------------
elif menu == "2. Assign Teaching Areas":
    st.header("Step 2: Assign Teachers to Classes & CBC Learning Areas")
    st.caption("Subjects are preloaded according to CBC curriculum standards for Lower Primary, Upper Primary, and Junior School.")

    teachers = supabase.table("teachers").select("*").execute().data
    classes = supabase.table("classes").select("*").execute().data

    if not teachers or not classes:
        st.warning("Please add at least one Teacher and one Class in Step 1 first.")
    else:
        t_opt = {f"{t.get('code', 'N/A')} - {t['name']}": t['id'] for t in teachers}
        c_map = {c['name']: (c['id'], c['category']) for c in classes}

        selected_c_name = st.selectbox("Select Class", list(c_map.keys()))
        c_id, c_category = c_map[selected_c_name]

        # Determine available learning areas based on CBC category
        if "Lower Primary" in c_category:
            allowed_sub_codes = ["MATHS", "ENG", "KISW", "ENV", "C.R.E", "C/A"]
        elif "Upper Primary" in c_category:
            allowed_sub_codes = ["MATHS", "ENG", "KISW", "C.R.E", "C/A", "AGR/NUT", "SCI/TECH", "SOC"]
        else: # Junior School
            allowed_sub_codes = ["MATHS", "ENG", "KISW", "C.R.E", "SOC", "AGRIC", "PRE", "INT SCI", "C.A.S"]

        sub_opt = {f"{code} - {CBC_SUBJECTS[code]['name']}": code for code in allowed_sub_codes}

        selected_sub_label = st.selectbox("Select CBC Learning Area", list(sub_opt.keys()))
        sub_code = sub_opt[selected_sub_label]

        selected_t_label = st.selectbox("Select Teacher", list(t_opt.keys()))
        t_id = t_opt[selected_t_label]

        periods = st.number_input("Periods per Week", min_value=1, max_value=15, value=5)

        if st.button("Save Teaching Allocation"):
            # Ensure subject exists in DB first or upsert it automatically
            sub_info = CBC_SUBJECTS[sub_code]
            sub_payload = {
                "code": sub_code,
                "name": sub_info["name"],
                "double_period_allowed": sub_info["double"]
            }
            supabase.table("subjects").upsert(sub_payload, on_conflict="code").execute()
            
            # Fetch subject ID
            s_db = supabase.table("subjects").select("id").eq("code", sub_code).execute().data
            s_id = s_db[0]['id']

            allocation_payload = {
                "class_id": c_id,
                "subject_id": s_id,
                "teacher_id": t_id,
                "periods_per_week": periods
            }
            supabase.table("allocations").upsert(allocation_payload, on_conflict="class_id,subject_id").execute()
            st.success(f"Assigned {sub_info['name']} to {selected_c_name} successfully!")
            st.rerun()

# ---------------------------------------------------------
# MODULE 3: DATA MANAGEMENT & DELETE CONTROLS
# ---------------------------------------------------------
elif menu == "3. Data Management":
    st.header("Manage & Delete Records")
    tab_t, tab_c, tab_a, tab_danger = st.tabs(["Teachers", "Classes", "Allocations", "Danger Zone"])

    with tab_t:
        teachers = supabase.table("teachers").select("*").execute().data
        if teachers:
            st.dataframe(pd.DataFrame(teachers)[["code", "name", "max_periods_per_day"]], use_container_width=True)
            to_del = st.selectbox("Select Teacher to Delete", [f"{t.get('code')} - {t['name']}" for t in teachers], key="del_t")
            if st.button("Delete Teacher"):
                t_code_sel = to_del.split(" - ")[0]
                t_id = [t['id'] for t in teachers if t.get('code') == t_code_sel][0]
                supabase.table("teachers").delete().eq("id", t_id).execute()
                st.success("Teacher deleted.")
                st.rerun()

    with tab_c:
        classes = supabase.table("classes").select("*").execute().data
        if classes:
            st.dataframe(pd.DataFrame(classes)[["name", "category"]], use_container_width=True)
            to_del_c = st.selectbox("Select Class to Delete", [c['name'] for c in classes], key="del_c")
            if st.button("Delete Class"):
                c_id = [c['id'] for c in classes if c['name'] == to_del_c][0]
                supabase.table("classes").delete().eq("id", c_id).execute()
                st.success("Class deleted.")
                st.rerun()

    with tab_a:
        allocs = supabase.table("allocations").select("id, classes(name), subjects(code), teachers(code, name), periods_per_week").execute().data
        if allocs:
            alloc_list = [f"{a['classes']['name']} | {a['subjects']['code']} | {a['teachers'].get('code')}" for a in allocs]
            to_del_a = st.selectbox("Select Allocation to Remove", alloc_list, key="del_a")
            if st.button("Remove Allocation"):
                idx = alloc_list.index(to_del_a)
                supabase.table("allocations").delete().eq("id", allocs[idx]['id']).execute()
                st.success("Allocation removed.")
                st.rerun()

    with tab_danger:
        st.error("Danger Zone")
        if st.button("Wipe Entire Database (Factory Reset)"):
            supabase.table("timetable_slots").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            supabase.table("allocations").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            supabase.table("teachers").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            supabase.table("classes").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            supabase.table("subjects").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            st.success("Database wiped.")
            st.rerun()

# ---------------------------------------------------------
# MODULE 4: GENERATION ENGINE (CUSTOM SECTION TIMINGS)
# ---------------------------------------------------------
elif menu == "4. Generate Timetable":
    st.header("Step 4: Generate School Timetable")
    st.info("Generating schedules according to section-specific lessons per day, period lengths, and Friday PPI/Games rules...")

    if st.button("Generate Complete Timetable"):
        allocs = supabase.table("allocations").select("*, classes(name, category), subjects(code, double_period_allowed), teachers(code, name, max_periods_per_day)").execute().data
        classes = supabase.table("classes").select("*").execute().data

        if not allocs or not classes:
            st.error("Please add classes and teaching allocations first.")
        else:
            supabase.table("timetable_slots").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()

            generated_slots = []
            busy_teachers = set()
            busy_classes = set()
            teacher_daily_count = {}
            class_day_subjects = set()

            # Section configurations
            # Lower Primary: 6 lessons/day (ends before lunch, 30 min)
            # Upper Primary: 7 lessons/day (1 after lunch, ends 2:35 PM, 35 min)
            # Junior School: 8 lessons/day (2 after lunch, ends 3:20 PM, 40 min)
            
            unassigned = []
            allocs.sort(key=lambda x: x['subjects']['double_period_allowed'], reverse=True)

            for c in classes:
                c_id = c['id']
                cat = c['category']
                
                if "Lower Primary" in cat:
                    total_p_day = 6
                    ppi_slots = { "FRI": 1 } # Friday Period 1 is PPI
                elif "Upper Primary" in cat:
                    total_p_day = 7
                    ppi_slots = { "FRI": 1 } # Friday Period 1 is PPI
                else: # Junior School
                    total_p_day = 8
                    ppi_slots = { "FRI": 8 } # Friday Period 8 is Games/PPI

                # Populate fixed PPI slots on Friday
                for day in DAYS_ORDER:
                    for p in range(1, total_p_day + 1):
                        if day in ppi_slots and p == ppi_slots[day]:
                            busy_classes.add((c_id, day, p))
                            generated_slots.append({
                                "day_of_week": day,
                                "period_number": p,
                                "class_id": c_id,
                                "subject_id": None,
                                "teacher_id": None,
                                "slot_type": "PPI"
                            })

            # Allocate subjects
            for alloc in allocs:
                c_id = alloc['class_id']
                s_id = alloc['subject_id']
                t_id = alloc['teacher_id']
                s_code = alloc['subjects']['code'].strip().upper()
                req_periods = alloc['periods_per_week']
                max_t_daily = alloc['teachers']['max_periods_per_day']
                is_double = alloc['subjects']['double_period_allowed']

                class_cat = [c['category'] for c in classes if c['id'] == c_id][0]
                max_p = 6 if "Lower Primary" in class_cat else (7 if "Upper Primary" in class_cat else 8)
                lesson_pool = [p for p in range(1, max_p + 1)]

                assigned_count = 0
                shuffled_days = DAYS_ORDER.copy()
                random.shuffle(shuffled_days)

                for day in shuffled_days:
                    if assigned_count >= req_periods:
                        break

                    curr_t_count = teacher_daily_count.get((t_id, day), 0)

                    # Double period constraint (Only Junior school subjects)
                    if is_double and (req_periods - assigned_count) >= 2:
                        for idx in range(len(lesson_pool) - 1):
                            p1 = lesson_pool[idx]
                            p2 = lesson_pool[idx + 1]
                            if p2 != p1 + 1: continue

                            if curr_t_count + 2 <= max_t_daily:
                                if (t_id, day, p1) not in busy_teachers and (t_id, day, p2) not in busy_teachers and \
                                   (c_id, day, p1) not in busy_classes and (c_id, day, p2) not in busy_classes:
                                    
                                    for sp in [p1, p2]:
                                        busy_teachers.add((t_id, day, sp))
                                        busy_classes.add((c_id, day, sp))
                                        generated_slots.append({
                                            "day_of_week": day, "period_number": sp,
                                            "class_id": c_id, "subject_id": s_id, "teacher_id": t_id, "slot_type": "LESSON"
                                        })
                                    teacher_daily_count[(t_id, day)] = curr_t_count + 2
                                    assigned_count += 2
                                    break

                    # Single period allocation
                    if not is_double or assigned_count < req_periods:
                        for p in lesson_pool:
                            if assigned_count >= req_periods: break
                            if curr_t_count + 1 <= max_t_daily:
                                if (t_id, day, p) not in busy_teachers and (c_id, day, p) not in busy_classes:
                                    busy_teachers.add((t_id, day, p))
                                    busy_classes.add((c_id, day, p))
                                    teacher_daily_count[(t_id, day)] = curr_t_count + 1
                                    generated_slots.append({
                                        "day_of_week": day, "period_number": p,
                                        "class_id": c_id, "subject_id": s_id, "teacher_id": t_id, "slot_type": "LESSON"
                                    })
                                    assigned_count += 1

                if assigned_count < req_periods:
                    unassigned.append(f"Class ID {c_id} - {s_code} ({req_periods - assigned_count} unassigned)")

            if generated_slots:
                supabase.table("timetable_slots").insert(generated_slots).execute()
                st.success("Timetable generated successfully!")

            if unassigned:
                st.warning("Some periods could not be placed due to daily teacher limits or slot constraints:")
                for u in unassigned:
                    st.write(f"- {u}")

# ---------------------------------------------------------
# MODULE 5: VIEW & EXPORT TIMETABLES
# ---------------------------------------------------------
elif menu == "5. View & Export Timetables":
    st.header("Step 5: View & Export Timetables")

    raw_data = supabase.table("timetable_slots").select(
        "day_of_week, period_number, slot_type, classes(name, category), subjects(code, name), teachers(code, name)"
    ).execute().data

    if not raw_data:
        st.info("No timetable generated yet. Please run Step 4.")
    else:
        formatted = []
        for d in raw_data:
            p_num = d['period_number']
            slot_type = d.get('slot_type', 'LESSON')
            t_code = d['teachers'].get('code', '') if d.get('teachers') else ""
            t_name = d['teachers'].get('name', '') if d.get('teachers') else ""
            c_name = d['classes']['name'] if d.get('classes') else ""
            s_code = d['subjects']['code'] if d.get('subjects') else ""

            if slot_type == "PPI":
                entry_text = "PPI / GAMES"
            else:
                entry_text = f"{s_code}\n({t_code})" if t_code else s_code

            formatted.append({
                "DAY": d['day_of_week'],
                "GRADE": c_name,
                "Period_Num": p_num,
                "TeacherCode": t_code,
                "TeacherName": t_name,
                "SubjectCode": s_code,
                "Entry": entry_text
            })

        df = pd.DataFrame(formatted)

        tab1, tab2, tab3 = st.tabs(["Master Timetable", "Class Timetables", "Teacher Timetables"])

        with tab1:
            st.title("KEA COMPREHENSIVE SCHOOL MASTER TIMETABLE")
            master_pivot = df.pivot_table(index=["DAY", "GRADE"], columns="Period_Num", values="Entry", aggfunc='first').fillna("-")
            st.dataframe(master_pivot, use_container_width=True)

            buffer_m = io.BytesIO()
            with pd.ExcelWriter(buffer_m, engine='xlsxwriter') as writer:
                master_pivot.to_excel(writer, sheet_name="Master Timetable")
            st.download_button("Export Master Timetable to Excel", data=buffer_m.getvalue(), file_name="KEA_Master_Timetable.xlsx", mime="application/vnd.ms-excel")

        with tab2:
            st.subheader("Individual Class Timetable")
            selected_class = st.selectbox("Select Grade / Class", sorted(df["GRADE"].unique()))
            class_df = df[df["GRADE"] == selected_class]
            
            pivot_class = class_df.pivot(index="Period_Num", columns="DAY", values="Entry").reindex(columns=DAYS_ORDER).fillna("FREE")
            st.dataframe(pivot_class, use_container_width=True)

            # Teacher Code Legend
            st.markdown("---")
            st.subheader("Teacher Code Reference Key")
            class_teachers = class_df[class_df["TeacherCode"] != ""][["TeacherCode", "TeacherName", "SubjectCode"]].drop_duplicates()
            if not class_teachers.empty:
                st.dataframe(class_teachers.rename(columns={"TeacherCode": "CODE", "TeacherName": "TEACHER NAME", "SubjectCode": "SUBJECT"}), hide_index=True, use_container_width=True)

        with tab3:
            st.subheader("Individual Teacher Schedule")
            teacher_dict = {f"{d['TeacherCode']} - {d['TeacherName']}": d['TeacherCode'] for d in formatted if d['TeacherCode']}
            if teacher_dict:
                sel_t_label = st.selectbox("Select Teacher", sorted(list(teacher_dict.keys())))
                sel_t_code = teacher_dict[sel_t_label]

                t_df = df[df["TeacherCode"] == sel_t_code]
                t_df["T_Entry"] = t_df["SubjectCode"] + " [" + t_df["GRADE"] + "]"
                
                pivot_t = t_df.pivot(index="Period_Num", columns="DAY", values="T_Entry").reindex(columns=DAYS_ORDER).fillna("FREE")
                st.dataframe(pivot_t, use_container_width=True)