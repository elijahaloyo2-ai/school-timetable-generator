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
    {"num": 1, "time": "08:20 - 09:00", "type": "lesson", "label": "Period 1"},
    {"num": 2, "time": "09:00 - 09:40", "type": "lesson", "label": "Period 2"},
    {"num": 3, "time": "09:40 - 09:50", "type": "break", "label": "Tea Break (10m)"},
    {"num": 4, "time": "09:50 - 10:30", "type": "lesson", "label": "Period 3"},
    {"num": 5, "time": "10:30 - 11:10", "type": "lesson", "label": "Period 4"},
    {"num": 6, "time": "11:10 - 11:30", "type": "break", "label": "2nd Break (20m)"},
    {"num": 7, "time": "11:30 - 12:10", "type": "lesson", "label": "Period 5"},
    {"num": 8, "time": "12:10 - 12:50", "type": "lesson", "label": "Period 6"},
    {"num": 9, "time": "12:50 - 14:00", "type": "break", "label": "Lunch Break (1h 10m)"},
    {"num": 10, "time": "14:00 - 14:40", "type": "lesson", "label": "Period 7"},
    {"num": 11, "time": "14:40 - 15:20", "type": "lesson", "label": "Period 8"},
    {"num": 12, "time": "15:20 - 16:00", "type": "activity", "label": "Games / PPI"}
]

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
        t_name = st.text_input("Teacher Name")
        t_max = st.number_input("Max Teaching Periods / Day", min_value=1, max_value=8, value=6)
        if st.button("Save Teacher"):
            if t_name:
                supabase.table("teachers").insert({"name": t_name, "max_periods_per_day": t_max}).execute()
                st.success(f"Added Teacher: {t_name}")
                st.rerun()

        st.subheader("Add Class")
        c_name = st.text_input("Class Name (e.g., Grade 8A)")
        if st.button("Save Class"):
            if c_name:
                supabase.table("classes").insert({"name": c_name}).execute()
                st.success(f"Added Class: {c_name}")
                st.rerun()

    with col2:
        st.subheader("Add Subject")
        s_code = st.text_input("Subject Code (e.g., MATH)")
        s_name = st.text_input("Subject Name")
        s_double = st.checkbox("Requires Double Periods (Consecutive Lessons)")
        if st.button("Save Subject"):
            if s_code and s_name:
                supabase.table("subjects").insert({"code": s_code, "name": s_name, "double_period_allowed": s_double}).execute()
                st.success(f"Added Subject: {s_name}")
                st.rerun()

    st.markdown("---")
    st.subheader("Assign Subject Allocations")
    
    teachers = supabase.table("teachers").select("*").execute().data
    classes = supabase.table("classes").select("*").execute().data
    subjects = supabase.table("subjects").select("*").execute().data

    if teachers and classes and subjects:
        t_opt = {t['name']: t['id'] for t in teachers}
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
    st.caption("Delete selected rows, allocations, or perform a full system reset if you made an error.")

    tab_t, tab_c, tab_s, tab_a, tab_danger = st.tabs(["Teachers", "Classes", "Subjects", "Allocations", "Danger Zone"])

    # Teachers Deletion
    with tab_t:
        teachers = supabase.table("teachers").select("*").execute().data
        if teachers:
            df_t = pd.DataFrame(teachers)
            st.dataframe(df_t[["name", "max_periods_per_day"]], use_container_width=True)
            to_delete_t = st.selectbox("Select Teacher to Delete", [t['name'] for t in teachers])
            if st.button("Delete Selected Teacher"):
                t_id = [t['id'] for t in teachers if t['name'] == to_delete_t][0]
                supabase.table("teachers").delete().eq("id", t_id).execute()
                st.success(f"Deleted Teacher: {to_delete_t}")
                st.rerun()
        else:
            st.info("No teachers registered.")

    # Classes Deletion
    with tab_c:
        classes = supabase.table("classes").select("*").execute().data
        if classes:
            df_c = pd.DataFrame(classes)
            st.dataframe(df_c[["name"]], use_container_width=True)
            to_delete_c = st.selectbox("Select Class to Delete", [c['name'] for c in classes])
            if st.button("Delete Selected Class"):
                c_id = [c['id'] for c in classes if c['name'] == to_delete_c][0]
                supabase.table("classes").delete().eq("id", c_id).execute()
                st.success(f"Deleted Class: {to_delete_c}")
                st.rerun()
        else:
            st.info("No classes registered.")

    # Subjects Deletion
    with tab_s:
        subjects = supabase.table("subjects").select("*").execute().data
        if subjects:
            df_s = pd.DataFrame(subjects)
            st.dataframe(df_s[["code", "name", "double_period_allowed"]], use_container_width=True)
            to_delete_s = st.selectbox("Select Subject to Delete", [s['code'] for s in subjects])
            if st.button("Delete Selected Subject"):
                s_id = [s['id'] for s in subjects if s['code'] == to_delete_s][0]
                supabase.table("subjects").delete().eq("id", s_id).execute()
                st.success(f"Deleted Subject: {to_delete_s}")
                st.rerun()
        else:
            st.info("No subjects registered.")

    # Allocations Deletion
    with tab_a:
        allocs = supabase.table("allocations").select("id, classes(name), subjects(code), teachers(name), periods_per_week").execute().data
        if allocs:
            alloc_list = [f"{a['classes']['name']} | {a['subjects']['code']} | {a['teachers']['name']}" for a in allocs]
            st.selectbox("Current Allocations", alloc_list)
            to_delete_a = st.selectbox("Select Allocation to Remove", alloc_list, key="del_alloc")
            if st.button("Delete Selected Allocation"):
                idx = alloc_list.index(to_delete_a)
                target_id = allocs[idx]['id']
                supabase.table("allocations").delete().eq("id", target_id).execute()
                st.success("Allocation removed!")
                st.rerun()
        else:
            st.info("No allocations defined.")

    # Danger Zone: Full Wipe
    with tab_danger:
        st.error("Danger Zone - Bulk Operations")
        if st.button("Clear Generated Timetables Only"):
            supabase.table("timetable_slots").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            st.success("Cleared all generated timetable records.")
            st.rerun()

        if st.button("Wipe Entire Database (Reset Everything)"):
            supabase.table("timetable_slots").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            supabase.table("allocations").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            supabase.table("teachers").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            supabase.table("classes").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            supabase.table("subjects").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            st.success("Database reset to factory default.")
            st.rerun()

# ---------------------------------------------------------
# MODULE 3: GENERATION ENGINE
# ---------------------------------------------------------
elif menu == "3. Generate Timetable":
    st.header("Step 3: Generate Master, Class & Teacher Timetables")
    st.info("Lessons start at 08:20 AM (40 min per lesson). Fixed breaks and Games/PPI are automatically inserted.")

    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

    if st.button("Generate Complete Timetable"):
        st.info("Running constraint solver...")
        
        allocs = supabase.table("allocations").select("*, classes(name), subjects(code, double_period_allowed), teachers(name, max_periods_per_day)").execute().data
        all_classes = supabase.table("classes").select("id").execute().data

        if not allocs:
            st.error("No subject allocations found. Add allocations in Step 1.")
        else:
            # Clear previous timetable output
            supabase.table("timetable_slots").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()

            generated_slots = []
            busy_teachers = set()     # (teacher_id, day, slot_num)
            busy_classes = set()      # (class_id, day, slot_num)
            teacher_daily_count = {} # (teacher_id, day) -> count
            class_day_subjects = set()

            lesson_slots = [b['num'] for b in BELL_SCHEDULE if b['type'] == 'lesson']

            # 1. Populate Fixed Breaks & Activity Periods Across All Classes
            for c in all_classes:
                c_id = c['id']
                for day in days:
                    for b in BELL_SCHEDULE:
                        if b['type'] == 'break':
                            busy_classes.add((c_id, day, b['num']))
                            generated_slots.append({"day_of_week": day, "period_number": b['num'], "class_id": c_id, "subject_id": None, "teacher_id": None})
                        elif b['type'] == 'activity':
                            busy_classes.add((c_id, day, b['num']))
                            activity_code = "GAMES" if day != "Friday" else "PPI"
                            generated_slots.append({"day_of_week": day, "period_number": b['num'], "class_id": c_id, "subject_id": None, "teacher_id": None})

            # Sort allocations: Double periods allocated first
            allocs.sort(key=lambda x: x['subjects']['double_period_allowed'], reverse=True)

            unassigned = []

            for alloc in allocs:
                c_id = alloc['class_id']
                s_id = alloc['subject_id']
                t_id = alloc['teacher_id']
                req_periods = alloc['periods_per_week']
                max_t_daily = alloc['teachers']['max_periods_per_day']
                is_double = alloc['subjects']['double_period_allowed']

                assigned_count = 0
                shuffled_days = days.copy()
                random.shuffle(shuffled_days)

                for day in shuffled_days:
                    if assigned_count >= req_periods:
                        break

                    curr_t_count = teacher_daily_count.get((t_id, day), 0)

                    # Handle Double Periods (2 consecutive lesson slots)
                    if is_double and (req_periods - assigned_count) >= 2:
                        for idx in range(len(lesson_slots) - 1):
                            p1 = lesson_slots[idx]
                            p2 = lesson_slots[idx + 1]

                            # Ensure p1 and p2 are strictly consecutive
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

                    # Handle Single Period Allocations
                    if not is_double or assigned_count < req_periods:
                        if (c_id, day, s_id) in class_day_subjects and not is_double:
                            continue

                        for p in lesson_slots:
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
                st.warning("Unassigned Slots due to schedule/teacher max limit constraints:")
                for u in unassigned:
                    st.write(f"- {u}")

# ---------------------------------------------------------
# MODULE 4: DISPLAY & EXPORT
# ---------------------------------------------------------
elif menu == "4. View & Export Timetables":
    st.header("Step 4: View & Export Timetables")

    raw_data = supabase.table("timetable_slots").select(
        "day_of_week, period_number, classes(name), subjects(code), teachers(name)"
    ).execute().data

    if not raw_data:
        st.info("No timetable generated yet. Please run Step 3.")
    else:
        bell_map = {b['num']: f"{b['label']}\n({b['time']})" for b in BELL_SCHEDULE}
        break_nums = [b['num'] for b in BELL_SCHEDULE if b['type'] != 'lesson']

        formatted = []
        for d in raw_data:
            p_num = d['period_number']
            t_name = d['teachers']['name'] if d.get('teachers') else ""
            c_name = d['classes']['name'] if d.get('classes') else ""
            s_code = d['subjects']['code'] if d.get('subjects') else ""

            # Check for Breaks & Games/PPI
            if p_num in break_nums:
                b_info = [b for b in BELL_SCHEDULE if b['num'] == p_num][0]
                if b_info['type'] == 'activity':
                    entry_text = "GAMES" if d['day_of_week'] != "Friday" else "PPI"
                else:
                    entry_text = b_info['label'].upper()
            else:
                entry_text = f"{s_code}\n({t_name})" if t_name else s_code

            formatted.append({
                "Day": d['day_of_week'],
                "Time Slot": bell_map.get(p_num, f"Slot {p_num}"),
                "Period_Num": p_num,
                "Class": c_name,
                "Subject": s_code,
                "Teacher": t_name,
                "Entry": entry_text
            })

        df = pd.DataFrame(formatted)
        days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

        tab1, tab2, tab3 = st.tabs(["Master Timetable", "Class Timetables", "Teacher Timetables"])

        with tab1:
            st.subheader("Master Overview")
            master_pivot = df.pivot_table(index=["Time Slot"], columns=["Day", "Class"], values="Subject", aggfunc=lambda x: ' '.join(x)).fillna("-")
            st.dataframe(master_pivot, use_container_width=True)

        with tab2:
            st.subheader("Class View")
            selected_class = st.selectbox("Select Class", sorted([c for c in df["Class"].unique() if c]))
            class_df = df[df["Class"] == selected_class].sort_values("Period_Num")
            pivot_class = class_df.pivot(index="Time Slot", columns="Day", values="Entry").reindex(columns=days_order).fillna("FREE")
            st.dataframe(pivot_class, use_container_width=True)

            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                pivot_class.to_excel(writer, sheet_name=selected_class)
            st.download_button(f"Export {selected_class} Schedule to Excel", data=buffer.getvalue(), file_name=f"{selected_class}_Timetable.xlsx", mime="application/vnd.ms-excel")

        with tab3:
            st.subheader("Teacher View")
            valid_teachers = sorted([t for t in df["Teacher"].unique() if t])
            if valid_teachers:
                selected_teacher = st.selectbox("Select Teacher", valid_teachers)
                teacher_df = df[df["Teacher"] == selected_teacher].sort_values("Period_Num")
                teacher_df["TeacherEntry"] = teacher_df["Subject"] + " [" + teacher_df["Class"] + "]"
                pivot_teacher = teacher_df.pivot(index="Time Slot", columns="Day", values="TeacherEntry").reindex(columns=days_order).fillna("FREE")
                st.dataframe(pivot_teacher, use_container_width=True)

                buffer_t = io.BytesIO()
                with pd.ExcelWriter(buffer_t, engine='xlsxwriter') as writer:
                    pivot_teacher.to_excel(writer, sheet_name=selected_teacher)
                st.download_button(f"Export {selected_teacher} Schedule to Excel", data=buffer_t.getvalue(), file_name=f"{selected_teacher}_Timetable.xlsx", mime="application/vnd.ms-excel")