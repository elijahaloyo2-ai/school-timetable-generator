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

# Navigation
menu = st.sidebar.selectbox(
    "Navigation", 
    ["1. Data Input & Rules", "2. Generate Timetable", "3. View & Export Timetables"]
)

# ---------------------------------------------------------
# MODULE 1: DATA INPUT & BREAK RULES
# ---------------------------------------------------------
if menu == "1. Data Input & Rules":
    st.header("Step 1: System Setup, Allocations & Fixed Breaks")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Add Teacher")
        t_name = st.text_input("Teacher Name")
        t_max = st.number_input("Max Periods / Day", min_value=1, max_value=10, value=6)
        if st.button("Save Teacher"):
            supabase.table("teachers").insert({"name": t_name, "max_periods_per_day": t_max}).execute()
            st.success(f"Added Teacher: {t_name}")

        st.subheader("Add Class")
        c_name = st.text_input("Class Name (e.g., Grade 8A)")
        if st.button("Save Class"):
            supabase.table("classes").insert({"name": c_name}).execute()
            st.success(f"Added Class: {c_name}")

    with col2:
        st.subheader("Add Subject")
        s_code = st.text_input("Subject Code (e.g., MATH)")
        s_name = st.text_input("Subject Name")
        s_double = st.checkbox("Requires Double Periods")
        if st.button("Save Subject"):
            supabase.table("subjects").insert({"code": s_code, "name": s_name, "double_period_allowed": s_double}).execute()
            st.success(f"Added Subject: {s_name}")

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

        if st.button("Add Allocation"):
            payload = {
                "class_id": c_opt[selected_c],
                "subject_id": s_opt[selected_s],
                "teacher_id": t_opt[selected_t],
                "periods_per_week": periods
            }
            supabase.table("allocations").upsert(payload, on_conflict="class_id,subject_id").execute()
            st.success("Allocation saved!")

# ---------------------------------------------------------
# MODULE 2: GENERATION ENGINE WITH BREAKS & DOUBLE PERIODS
# ---------------------------------------------------------
elif menu == "2. Generate Timetable":
    st.header("Step 2: Constraint Engine Setup & Scheduling")
    
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    
    col_cfg1, col_cfg2 = st.columns(2)
    with col_cfg1:
        periods_per_day = st.slider("Total Periods Per Day", min_value=6, max_value=10, value=8)
        break_period = st.number_input("Short Break Period Number", min_value=1, max_value=periods_per_day, value=3)
    
    with col_cfg2:
        lunch_period = st.number_input("Lunch Break Period Number", min_value=1, max_value=periods_per_day, value=6)
        double_period_handling = st.checkbox("Strictly enforce paired double periods", value=True)

    if st.button("Generate Complete Timetable"):
        st.info("Executing constraint satisfaction solver with fixed break and double-period rules...")
        
        allocs = supabase.table("allocations").select("*, classes(name), subjects(code, double_period_allowed), teachers(name, max_periods_per_day)").execute().data
        
        if not allocs:
            st.error("No allocations found in database.")
        else:
            # Reset timetable database
            supabase.table("timetable_slots").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            
            # Reserved slot maps & status trackers
            generated_slots = []
            busy_teachers = set()      # (teacher_id, day, period)
            busy_classes = set()       # (class_id, day, period)
            teacher_daily_count = {}  # (teacher_id, day) -> count
            class_day_subjects = set() # (class_id, day, subject_id) -> Avoid duplicate single subjects in 1 day

            # 1. Insert Fixed Breaks Across All Classes
            all_classes = supabase.table("classes").select("id").execute().data
            break_subject = supabase.table("subjects").select("id").eq("code", "BREAK").execute().data
            lunch_subject = supabase.table("subjects").select("id").eq("code", "LUNCH").execute().data
            
            break_s_id = break_subject[0]['id'] if break_subject else None
            lunch_s_id = lunch_subject[0]['id'] if lunch_subject else None

            for c in all_classes:
                c_id = c['id']
                for day in days:
                    # Mark break & lunch periods as busy for classes
                    busy_classes.add((c_id, day, break_period))
                    busy_classes.add((c_id, day, lunch_period))
                    
                    if break_s_id:
                        generated_slots.append({"day_of_week": day, "period_number": break_period, "class_id": c_id, "subject_id": break_s_id, "teacher_id": None})
                    if lunch_s_id:
                        generated_slots.append({"day_of_week": day, "period_number": lunch_period, "class_id": c_id, "subject_id": lunch_s_id, "teacher_id": None})

            unassigned = []

            # Sort allocations: Process subjects requiring double periods first
            allocs.sort(key=lambda x: x['subjects']['double_period_allowed'], reverse=True)

            for alloc in allocs:
                c_id = alloc['class_id']
                s_id = alloc['subject_id']
                t_id = alloc['teacher_id']
                req_periods = alloc['periods_per_week']
                max_t_daily = alloc['teachers']['max_periods_per_day']
                is_double = alloc['subjects']['double_period_allowed'] and double_period_handling

                assigned_count = 0
                shuffled_days = days.copy()
                random.shuffle(shuffled_days)

                for day in shuffled_days:
                    if assigned_count >= req_periods:
                        break

                    curr_t_count = teacher_daily_count.get((t_id, day), 0)

                    # Handle Double Period Assignment
                    if is_double and (req_periods - assigned_count) >= 2:
                        for p in range(1, periods_per_day):
                            p_next = p + 1

                            # Double periods cannot cross fixed breaks
                            if p in (break_period, lunch_period) or p_next in (break_period, lunch_period):
                                continue

                            # Verify constraints for period p and p+1
                            if curr_t_count + 2 <= max_t_daily:
                                if (t_id, day, p) not in busy_teachers and (t_id, day, p_next) not in busy_teachers and \
                                   (c_id, day, p) not in busy_classes and (c_id, day, p_next) not in busy_classes:
                                    
                                    # Assign Double Slot
                                    for slot_p in [p, p_next]:
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

                    # Handle Single Period Assignment
                    if not is_double or assigned_count < req_periods:
                        if (c_id, day, s_id) in class_day_subjects and not is_double:
                            continue

                        for p in range(1, periods_per_day + 1):
                            if assigned_count >= req_periods:
                                break
                            if p in (break_period, lunch_period):
                                continue

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
                    unassigned.append(f"{alloc['classes']['name']} - {alloc['subjects']['code']} ({req_periods - assigned_count} slots missing)")

            # Commit to database
            if generated_slots:
                supabase.table("timetable_slots").insert(generated_slots).execute()
                st.success(f"Successfully scheduled {len(generated_slots)} slots including breaks & double periods!")

            if unassigned:
                st.warning("Unassigned Allocations due to schedule constraints:")
                for u in unassigned:
                    st.write(f"- {u}")

# ---------------------------------------------------------
# MODULE 3: DISPLAY & EXPORT
# ---------------------------------------------------------
elif menu == "3. View & Export Timetables":
    st.header("Step 3: Export Master, Class & Teacher Views")

    raw_data = supabase.table("timetable_slots").select(
        "day_of_week, period_number, classes(name), subjects(code), teachers(name)"
    ).execute().data

    if not raw_data:
        st.info("No timetable generated yet.")
    else:
        formatted = []
        for d in raw_data:
            t_name = d['teachers']['name'] if d.get('teachers') else "N/A"
            c_name = d['classes']['name'] if d.get('classes') else "N/A"
            s_code = d['subjects']['code'] if d.get('subjects') else "FREE"
            
            formatted.append({
                "Day": d['day_of_week'],
                "Period": f"Period {d['period_number']}",
                "Period_Num": d['period_number'],
                "Class": c_name,
                "Subject": s_code,
                "Teacher": t_name,
                "ClassEntry": s_code if s_code in ["BREAK", "LUNCH"] else f"{s_code}\n({t_name})"
            })

        df = pd.DataFrame(formatted)
        days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

        tab1, tab2, tab3 = st.tabs(["Master Timetable", "Class Views", "Teacher Views"])

        with tab1:
            st.subheader("Master Overview")
            master_pivot = df.pivot_table(index=["Day", "Period"], columns="Class", values="Subject", aggfunc=lambda x: ' '.join(x)).fillna("-")
            st.dataframe(master_pivot, use_container_width=True)

        with tab2:
            st.subheader("Class Schedule")
            selected_class = st.selectbox("Select Class", sorted([c for c in df["Class"].unique() if c != "N/A"]))
            class_df = df[df["Class"] == selected_class].sort_values("Period_Num")
            pivot_class = class_df.pivot(index="Period", columns="Day", values="ClassEntry").reindex(columns=days_order).fillna("FREE")
            st.dataframe(pivot_class, use_container_width=True)

            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                pivot_class.to_excel(writer, sheet_name=selected_class)
            st.download_button(f"Download {selected_class} Schedule (Excel)", data=buffer.getvalue(), file_name=f"{selected_class}_Timetable.xlsx", mime="application/vnd.ms-excel")

        with tab3:
            st.subheader("Teacher Schedule")
            valid_teachers = sorted([t for t in df["Teacher"].unique() if t != "N/A"])
            if valid_teachers:
                selected_teacher = st.selectbox("Select Teacher", valid_teachers)
                teacher_df = df[df["Teacher"] == selected_teacher].sort_values("Period_Num")
                teacher_df["TeacherEntry"] = teacher_df["Subject"] + " [" + teacher_df["Class"] + "]"
                pivot_teacher = teacher_df.pivot(index="Period", columns="Day", values="TeacherEntry").reindex(columns=days_order).fillna("FREE")
                st.dataframe(pivot_teacher, use_container_width=True)

                buffer_t = io.BytesIO()
                with pd.ExcelWriter(buffer_t, engine='xlsxwriter') as writer:
                    pivot_teacher.to_excel(writer, sheet_name=selected_teacher)
                st.download_button(f"Download {selected_teacher} Schedule (Excel)", data=buffer_t.getvalue(), file_name=f"{selected_teacher}_Timetable.xlsx", mime="application/vnd.ms-excel")