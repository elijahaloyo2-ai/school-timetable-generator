import streamlit as st
import pandas as pd
from supabase import create_client, Client
import random
import io

# Page Configuration
st.set_page_config(page_title="Automated School Timetable System", layout="wide")
st.title("Automated School Timetable Generator")

SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")

@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

# Define Exact School Bell Schedule
BELL_SCHEDULE = [
    {"num": 1, "time": "8:20 - 9:00", "type": "lesson", "label": "Lesson 1"},
    {"num": 2, "time": "9:00 - 9:40", "type": "lesson", "label": "Lesson 2"},
    {"num": 3, "time": "9:40 - 9:50", "type": "break", "label": "BREAK"},
    {"num": 4, "time": "9:50 - 10:30", "type": "lesson", "label": "Lesson 3"},
    {"num": 5, "time": "10:30 - 11:10", "type": "lesson", "label": "Lesson 4"},
    {"num": 6, "time": "11:10 - 11:30", "type": "break", "label": "BREAK"},
    {"num": 7, "time": "11:30 - 12:10", "type": "lesson", "label": "Lesson 5"},
    {"num": 8, "time": "12:10 - 12:50", "type": "lesson", "label": "Lesson 6"},
    {"num": 9, "time": "12:50 - 2:00", "type": "break", "label": "LUNCH"},
    {"num": 10, "time": "2:00 - 2:40", "type": "lesson", "label": "Lesson 7"},
    {"num": 11, "time": "2:40 - 3:20", "type": "lesson", "label": "Lesson 8"},
    {"num": 12, "time": "3:20 - 4:00", "type": "activity", "label": "GAMES / PPI"}
]

DOUBLE_ALLOWED_SUBJECTS = {"INT SCI", "PRE", "AGRIC", "C.A.S"}
DAYS_ORDER = ["MON", "TUE", "WED", "THUR", "FRI"]
PERIOD_NUMBERS = [b['num'] for b in BELL_SCHEDULE]
TIME_SLOT_LABELS = {b['num']: f"{b['time']}\n({b['label']})" for b in BELL_SCHEDULE}

# Navigation
menu = st.sidebar.selectbox(
    "Navigation", 
    ["1. Setup & Data Entry", "2. Data Management & Delete", "3. Generate Timetable", "4. View & Export Timetables"]
)

# ---------------------------------------------------------
# MODULE 1: SETUP & DATA ENTRY
# ---------------------------------------------------------
if menu == "1. Setup & Data Entry":
    st.header("Step 1: System Setup & Allocations")
    
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
                st.error("Please enter both Teacher Name and Teacher Code.")

        st.subheader("Add Class")
        c_name = st.text_input("Class Name (e.g., GRADE 7, GRADE 8, GRADE 9)")
        if st.button("Save Class"):
            if c_name:
                supabase.table("classes").insert({"name": c_name.upper()}).execute()
                st.success(f"Added Class: {c_name.upper()}")
                st.rerun()

    with col2:
        st.subheader("Add Subject")
        s_code = st.text_input("Subject Code (e.g., MATHS, ENG, INT SCI, PRE, AGRIC, C.A.S)")
        s_name = st.text_input("Subject Name")
        
        is_double_eligible = s_code.strip().upper() in DOUBLE_ALLOWED_SUBJECTS if s_code else False
        
        if is_double_eligible:
            s_double = st.checkbox("Requires Double Periods (Consecutive Lessons)", value=True)
        else:
            st.caption("ℹ️ Only INT SCI, PRE, AGRIC, and C.A.S can be configured as double lessons.")
            s_double = False

        if st.button("Save Subject"):
            if s_code and s_name:
                supabase.table("subjects").insert({"code": s_code.strip().upper(), "name": s_name, "double_period_allowed": s_double}).execute()
                st.success(f"Added Subject: {s_name}")
                st.rerun()

    st.markdown("---")
    st.subheader("Assign Subject Allocations")
    
    teachers = supabase.table("teachers").select("*").execute().data
    classes = supabase.table("classes").select("*").execute().data
    subjects = supabase.table("subjects").select("*").execute().data

    if teachers and classes and subjects:
        t_opt = {f"{t.get('code', 'N/A')} - {t['name']}": t['id'] for t in teachers}
        c_opt = {c['name']: c['id'] for c in classes}
        s_opt = {s['name']: s['id'] for s in subjects}

        col_a, col_b, col_c, col_d = st.columns(4)
        with col_a:
            selected_c = st.selectbox("Select Class", list(c_opt.keys()))
        with col_b:
            selected_s = st.selectbox("Select Subject", list(s_opt.keys()))
        with col_c:
            selected_t = st.selectbox("Select Teacher", list(t_opt.keys()))
        with col_d:
            periods = st.number_input("Periods per Week", min_value=1, max_value=15, value=5)

        if st.button("Save Allocation"):
            payload = {
                "class_id": c_opt[selected_c],
                "subject_id": s_opt[selected_s],
                "teacher_id": t_opt[selected_t],
                "periods_per_week": periods
            }
            supabase.table("allocations").upsert(payload, on_conflict="class_id,subject_id").execute()
            st.success("Allocation saved successfully!")
            st.rerun()

# ---------------------------------------------------------
# MODULE 2: DATA MANAGEMENT & DELETE CONTROLS
# ---------------------------------------------------------
elif menu == "2. Data Management & Delete":
    st.header("Manage & Delete Records")
    tab_t, tab_c, tab_s, tab_a, tab_danger = st.tabs(["Teachers", "Classes", "Subjects", "Allocations", "Danger Zone"])

    with tab_t:
        teachers = supabase.table("teachers").select("*").execute().data
        if teachers:
            st.dataframe(pd.DataFrame(teachers)[["code", "name", "max_periods_per_day"]], use_container_width=True)
            to_delete_t = st.selectbox("Select Teacher to Delete", [f"{t.get('code', 'N/A')} - {t['name']}" for t in teachers])
            if st.button("Delete Selected Teacher"):
                t_code_selected = to_delete_t.split(" - ")[0]
                t_id = [t['id'] for t in teachers if t.get('code') == t_code_selected or t['name'] == to_delete_t][0]
                supabase.table("teachers").delete().eq("id", t_id).execute()
                st.success(f"Deleted Teacher: {to_delete_t}")
                st.rerun()

    with tab_c:
        classes = supabase.table("classes").select("*").execute().data
        if classes:
            st.dataframe(pd.DataFrame(classes)[["name"]], use_container_width=True)
            to_delete_c = st.selectbox("Select Class to Delete", [c['name'] for c in classes])
            if st.button("Delete Selected Class"):
                c_id = [c['id'] for c in classes if c['name'] == to_delete_c][0]
                supabase.table("classes").delete().eq("id", c_id).execute()
                st.success(f"Deleted Class: {to_delete_c}")
                st.rerun()

    with tab_s:
        subjects = supabase.table("subjects").select("*").execute().data
        if subjects:
            st.dataframe(pd.DataFrame(subjects)[["code", "name", "double_period_allowed"]], use_container_width=True)
            to_delete_s = st.selectbox("Select Subject to Delete", [s['code'] for s in subjects])
            if st.button("Delete Selected Subject"):
                s_id = [s['id'] for s in subjects if s['code'] == to_delete_s][0]
                supabase.table("subjects").delete().eq("id", s_id).execute()
                st.success(f"Deleted Subject: {to_delete_s}")
                st.rerun()

    with tab_a:
        allocs = supabase.table("allocations").select("id, classes(name), subjects(code), teachers(code, name), periods_per_week").execute().data
        if allocs:
            alloc_list = [f"{a['classes']['name']} | {a['subjects']['code']} | {a['teachers'].get('code', 'N/A')}" for a in allocs]
            to_delete_a = st.selectbox("Select Allocation to Remove", alloc_list, key="del_alloc")
            if st.button("Delete Selected Allocation"):
                idx = alloc_list.index(to_delete_a)
                target_id = allocs[idx]['id']
                supabase.table("allocations").delete().eq("id", target_id).execute()
                st.success("Allocation removed!")
                st.rerun()

    with tab_danger:
        st.error("Danger Zone")
        if st.button("Wipe Entire Database (Reset Everything)"):
            supabase.table("timetable_slots").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            supabase.table("allocations").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            supabase.table("teachers").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            supabase.table("classes").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            supabase.table("subjects").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            st.success("Database reset to default.")
            st.rerun()

# ---------------------------------------------------------
# MODULE 3: GENERATION ENGINE
# ---------------------------------------------------------
elif menu == "3. Generate Timetable":
    st.header("Step 3: Generate Master, Class & Teacher Timetables")
    st.info("Generating timetable following time-slot constraints and break intervals...")

    days = DAYS_ORDER

    if st.button("Generate Complete Timetable"):
        allocs = supabase.table("allocations").select("*, classes(name), subjects(code, double_period_allowed), teachers(code, name, max_periods_per_day)").execute().data
        all_classes = supabase.table("classes").select("id").execute().data

        if not allocs:
            st.error("No subject allocations found.")
        else:
            supabase.table("timetable_slots").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()

            generated_slots = []
            busy_teachers = set()
            busy_classes = set()
            teacher_daily_count = {}
            class_day_subjects = set()

            all_lesson_slots = [b['num'] for b in BELL_SCHEDULE if b['type'] == 'lesson']

            for c in all_classes:
                c_id = c['id']
                for day in days:
                    for b in BELL_SCHEDULE:
                        if b['type'] in ['break', 'activity']:
                            busy_classes.add((c_id, day, b['num']))
                            generated_slots.append({"day_of_week": day, "period_number": b['num'], "class_id": c_id, "subject_id": None, "teacher_id": None})

            allocs.sort(key=lambda x: (
                x['subjects']['code'] in ['MATHS', 'MATH', 'ENG', 'ENGLISH'],
                x['subjects']['code'] in DOUBLE_ALLOWED_SUBJECTS and x['subjects']['double_period_allowed']
            ), reverse=True)

            unassigned = []

            for alloc in allocs:
                c_id = alloc['class_id']
                s_id = alloc['subject_id']
                t_id = alloc['teacher_id']
                s_code = alloc['subjects']['code'].strip().upper()
                req_periods = alloc['periods_per_week']
                max_t_daily = alloc['teachers']['max_periods_per_day']

                is_double = (s_code in DOUBLE_ALLOWED_SUBJECTS) and alloc['subjects']['double_period_allowed']

                if s_code in ["MATHS", "MATH"]:
                    allowed_slots = [1, 2, 4, 5]
                elif s_code in ["ENG", "ENGLISH"]:
                    allowed_slots = [1, 2, 4, 5, 7, 8]
                else:
                    allowed_slots = all_lesson_slots

                assigned_count = 0
                shuffled_days = days.copy()
                random.shuffle(shuffled_days)

                for day in shuffled_days:
                    if assigned_count >= req_periods:
                        break

                    curr_t_count = teacher_daily_count.get((t_id, day), 0)

                    if is_double and (req_periods - assigned_count) >= 2:
                        for idx in range(len(allowed_slots) - 1):
                            p1 = allowed_slots[idx]
                            p2 = allowed_slots[idx + 1]

                            if p2 != p1 + 1:
                                continue

                            if curr_t_count + 2 <= max_t_daily:
                                if (t_id, day, p1) not in busy_teachers and (t_id, day, p2) not in busy_teachers and \
                                   (c_id, day, p1) not in busy_classes and (c_id, day, p2) not in busy_classes:
                                    
                                    for slot_p in [p1, p2]:
                                        busy_teachers.add((t_id, day, slot_p))
                                        busy_classes.add((c_id, day, slot_p))
                                        generated_slots.append({
                                            "day_of_week": day,
                                            "period_number": slot_p,
                                            "class_id": c_id,
                                            "subject_id": s_id,
                                            "teacher_id": t_id
                                        })
                                    
                                    teacher_daily_count[(t_id, day)] = curr_t_count + 2
                                    assigned_count += 2
                                    class_day_subjects.add((c_id, day, s_id))
                                    break

                    if not is_double or assigned_count < req_periods:
                        if (c_id, day, s_id) in class_day_subjects and not is_double:
                            continue

                        for p in allowed_slots:
                            if assigned_count >= req_periods:
                                break

                            if curr_t_count + 1 <= max_t_daily:
                                if (t_id, day, p) not in busy_teachers and (c_id, day, p) not in busy_classes:
                                    busy_teachers.add((t_id, day, p))
                                    busy_classes.add((c_id, day, p))
                                    class_day_subjects.add((c_id, day, s_id))
                                    teacher_daily_count[(t_id, day)] = curr_t_count + 1

                                    generated_slots.append({
                                        "day_of_week": day,
                                        "period_number": p,
                                        "class_id": c_id,
                                        "subject_id": s_id,
                                        "teacher_id": t_id
                                    })
                                    assigned_count += 1
                                    curr_t_count += 1

                if assigned_count < req_periods:
                    unassigned.append(f"{alloc['classes']['name']} - {alloc['subjects']['code']} ({req_periods - assigned_count} unassigned)")

            if generated_slots:
                supabase.table("timetable_slots").insert(generated_slots).execute()
                st.success("Complete timetable generated successfully!")

            if unassigned:
                st.warning("Unassigned Slots due to constraints:")
                for u in unassigned:
                    st.write(f"- {u}")

# ---------------------------------------------------------
# MODULE 4: DISPLAY & EXPORT (SAFE INDEX REINDEXING)
# ---------------------------------------------------------
elif menu == "4. View & Export Timetables":
    st.header("Step 4: View & Export Timetables")

    raw_data = supabase.table("timetable_slots").select(
        "day_of_week, period_number, classes(name), subjects(code, name), teachers(code, name)"
    ).execute().data

    if not raw_data:
        st.info("No timetable generated yet. Please run Step 3.")
    else:
        formatted = []
        for d in raw_data:
            p_num = d['period_number']
            t_code = d['teachers'].get('code', '') if d.get('teachers') else ""
            t_name = d['teachers'].get('name', '') if d.get('teachers') else ""
            c_name = d['classes']['name'] if d.get('classes') else ""
            s_code = d['subjects']['code'] if d.get('subjects') else ""
            s_name = d['subjects']['name'] if d.get('subjects') else ""

            b_info = [b for b in BELL_SCHEDULE if b['num'] == p_num][0]

            if b_info['type'] == 'break':
                entry_text = b_info['label']
            elif b_info['type'] == 'activity':
                entry_text = "GAMES" if d['day_of_week'] != "FRI" else "PPI"
            else:
                entry_text = f"{s_code}\n({t_code})" if t_code else s_code

            formatted.append({
                "DAY": d['day_of_week'],
                "GRADE": c_name,
                "Period_Num": p_num,
                "SubjectCode": s_code,
                "SubjectName": s_name,
                "TeacherCode": t_code,
                "TeacherName": t_name,
                "Entry": entry_text
            })

        df = pd.DataFrame(formatted)

        tab1, tab2, tab3 = st.tabs(["KEA Master Timetable", "Individual Class Timetable", "Teacher Timetable"])

        # 1. MASTER TIMETABLE VIEW
        with tab1:
            st.title("KEA JUNIOR SCHOOL MASTER TIME TABLE 2027")

            master_pivot = df.pivot_table(
                index=["DAY", "GRADE"],
                columns="Period_Num",
                values="Entry",
                aggfunc='first'
            ).fillna("-")

            # Rename integer columns to exact time slot labels
            master_pivot.rename(columns=TIME_SLOT_LABELS, inplace=True)
            st.dataframe(master_pivot, use_container_width=True)

            col_l1, col_l2 = st.columns(2)

            with col_l1:
                st.subheader("GRADE TEACHERS")
                all_teachers = (
                    df[df["TeacherCode"] != ""]
                    [["TeacherCode", "TeacherName", "GRADE"]]
                    .drop_duplicates()
                    .sort_values("GRADE")
                )
                if not all_teachers.empty:
                    gt_df = all_teachers[["GRADE", "TeacherName"]].rename(columns={"GRADE": "Grade", "TeacherName": "Teacher"})
                    st.dataframe(gt_df, hide_index=True, use_container_width=True)

            with col_l2:
                st.subheader("TEACHER CODE LEGEND")
                t_legend = (
                    df[df["TeacherCode"] != ""]
                    [["TeacherCode", "TeacherName"]]
                    .drop_duplicates()
                    .sort_values("TeacherCode")
                )
                if not t_legend.empty:
                    st.dataframe(t_legend.rename(columns={"TeacherCode": "CODE", "TeacherName": "TEACHER NAME"}), hide_index=True, use_container_width=True)

            buffer_m = io.BytesIO()
            with pd.ExcelWriter(buffer_m, engine='xlsxwriter') as writer:
                master_pivot.to_excel(writer, sheet_name="Master Timetable")
            st.download_button("Export KEA Master Timetable to Excel", data=buffer_m.getvalue(), file_name="KEA_Master_Timetable.xlsx", mime="application/vnd.ms-excel")

        # 2. CLASS TIMETABLE VIEW
        with tab2:
            st.subheader("Individual Class Timetable")
            selected_class = st.selectbox("Select Grade / Class", sorted([c for c in df["GRADE"].unique() if c]))
            class_df = df[df["GRADE"] == selected_class]
            
            pivot_class = class_df.pivot(
                index="Period_Num", 
                columns="DAY", 
                values="Entry"
            ).reindex(index=PERIOD_NUMBERS, columns=DAYS_ORDER).fillna("FREE")

            # Safely replace Period Number index with Bell Schedule Time Labels
            pivot_class.index = [TIME_SLOT_LABELS[i] for i in pivot_class.index]
            st.dataframe(pivot_class, use_container_width=True)

            st.markdown("---")
            st.subheader("Teacher Code Reference Key")
            class_teachers = (
                class_df[class_df["TeacherCode"] != ""]
                [["TeacherCode", "TeacherName", "SubjectCode", "SubjectName"]]
                .drop_duplicates()
                .sort_values("TeacherCode")
            )
            if not class_teachers.empty:
                st.dataframe(class_teachers.rename(columns={"TeacherCode": "CODE", "TeacherName": "TEACHER NAME", "SubjectCode": "SUB CODE", "SubjectName": "SUBJECT NAME"}), hide_index=True, use_container_width=True)

        # 3. TEACHER TIMETABLE VIEW (FIXED)
        with tab3:
            st.subheader("Individual Teacher Schedule")
            teacher_legend_dict = {f"{d['TeacherCode']} - {d['TeacherName']}": d['TeacherCode'] for d in formatted if d['TeacherCode']}
            
            if teacher_legend_dict:
                selected_t_label = st.selectbox("Select Teacher", sorted(list(teacher_legend_dict.keys())))
                selected_t_code = teacher_legend_dict[selected_t_label]

                teacher_df = df[df["TeacherCode"] == selected_t_code]
                teacher_df["TeacherEntry"] = teacher_df["SubjectCode"] + " [" + teacher_df["GRADE"] + "]"
                
                # Reindex safely across all 12 periods and all 5 days
                pivot_teacher = teacher_df.pivot(
                    index="Period_Num", 
                    columns="DAY", 
                    values="TeacherEntry"
                ).reindex(index=PERIOD_NUMBERS, columns=DAYS_ORDER).fillna("FREE")

                # Map Period Number index to Bell Schedule Time Labels safely
                pivot_teacher.index = [TIME_SLOT_LABELS[i] for i in pivot_teacher.index]
                st.dataframe(pivot_teacher, use_container_width=True)