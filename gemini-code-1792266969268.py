import streamlit as st
import pandas as pd
from supabase import create_client, Client
import random
import io

# Setup Supabase Connection
st.set_page_config(page_title="Automated School Timetable System", layout="wide")
st.title("Automated School Timetable Generator")

SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")

@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

# Sidebar Setup & Navigation
menu = st.sidebar.selectbox("Navigation", ["1. Data Input", "2. Generate Timetable", "3. View & Export Timetables"])

# ---------------------------------------------------------
# MODULE 1: DATA INPUT
# ---------------------------------------------------------
if menu == "1. Data Input":
    st.header("Step 1: System Setup & Allocations")
    
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
        s_double = st.checkbox("Allow Double Periods")
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

        selected_c = st.selectbox("Select Class", list(c_opt.keys()))
        selected_s = st.selectbox("Select Subject", list(s_opt.keys()))
        selected_t = st.selectbox("Select Teacher", list(t_opt.keys()))
        periods = st.number_input("Periods per Week", min_value=1, max_value=15, value=5)

        if st.button("Add Allocation"):
            payload = {
                "class_id": c_opt[selected_c],
                "subject_id": s_opt[selected_s],
                "teacher_id": t_opt[selected_t],
                "periods_per_week": periods
            }
            supabase.table("allocations").upsert(payload, on_conflict="class_id,subject_id").execute()
            st.success("Allocation updated successfully!")

# ---------------------------------------------------------
# MODULE 2: GENERATION ENGINE
# ---------------------------------------------------------
elif menu == "2. Generate Timetable":
    st.header("Step 2: Automated Schedule Generation")
    
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    periods_per_day = st.slider("Periods Per Day", min_value=4, max_value=10, value=8)

    if st.button("Generate Complete Timetable"):
        st.info("Running constraint optimization engine...")
        
        # Load Data
        allocs = supabase.table("allocations").select("*, classes(name), subjects(code), teachers(name, max_periods_per_day)").execute().data
        
        if not allocs:
            st.error("No allocations found. Please setup allocations in Step 1 first.")
        else:
            # Clear previous runs
            supabase.table("timetable_slots").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            
            # Constraint Satisfaction Generator
            generated_slots = []
            teacher_daily_count = {} # (teacher_id, day) -> count
            busy_teachers = set()     # (teacher_id, day, period)
            busy_classes = set()      # (class_id, day, period)
            class_day_subjects = set()# (class_id, day, subject_id) -> Avoid repetition

            unassigned = []

            for alloc in allocs:
                c_id = alloc['class_id']
                s_id = alloc['subject_id']
                t_id = alloc['teacher_id']
                req_periods = alloc['periods_per_week']
                max_t_daily = alloc['teachers']['max_periods_per_day']

                assigned_count = 0

                # Shuffle days to balance distribution across the week
                shuffled_days = days.copy()
                random.shuffle(shuffled_days)

                for day in shuffled_days:
                    if assigned_count >= req_periods:
                        break

                    # Rule: Avoid unnecessary repetition of same subject in one day
                    if (c_id, day, s_id) in class_day_subjects:
                        continue

                    for p in range(1, periods_per_day + 1):
                        if assigned_count >= req_periods:
                            break

                        # Check Teacher Max Daily Rule
                        curr_t_count = teacher_daily_count.get((t_id, day), 0)
                        if curr_t_count >= max_t_daily:
                            break

                        # Hard Conflict Rules: Teacher or Class double-booking
                        if (t_id, day, p) not in busy_teachers and (c_id, day, p) not in busy_classes:
                            # Assign Slot
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

                if assigned_count < req_periods:
                    unassigned.append(f"{alloc['classes']['name']} - {alloc['subjects']['code']} ({req_periods - assigned_count} unassigned)")

            # Batch write to Supabase
            if generated_slots:
                supabase.table("timetable_slots").insert(generated_slots).execute()
                st.success(f"Generated {len(generated_slots)} timetable slots successfully!")

            if unassigned:
                st.warning("Could not allocate all periods due to schedule constraints:")
                for item in unassigned:
                    st.write(f"- {item}")

# ---------------------------------------------------------
# MODULE 3: VIEWS & EXPORTS
# ---------------------------------------------------------
elif menu == "3. View & Export Timetables":
    st.header("Step 3: Master, Class, & Teacher Timetables")

    raw_data = supabase.table("timetable_slots").select(
        "day_of_week, period_number, classes(name), subjects(code), teachers(name)"
    ).execute().data

    if not raw_data:
        st.info("No timetable generated yet. Run Step 2.")
    else:
        df = pd.DataFrame([
            {
                "Day": d['day_of_week'],
                "Period": f"Period {d['period_number']}",
                "Class": d['classes']['name'],
                "Subject": d['subjects']['code'],
                "Teacher": d['teachers']['name'],
                "Entry": f"{d['subjects']['code']}\n({d['teachers']['name']})" if 'teachers' in d else d['subjects']['code']
            } for d in raw_data
        ])

        tab1, tab2, tab3 = st.tabs(["Master School Timetable", "Class Timetables", "Teacher Timetables"])

        days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

        with tab1:
            st.subheader("Master Overview")
            master_df = df.pivot_table(index=["Day", "Period"], columns="Class", values="Subject", aggfunc=lambda x: ' '.join(x)).fillna("-")
            st.dataframe(master_df, use_container_width=True)

        with tab2:
            st.subheader("Class View")
            selected_class = st.selectbox("Select Class View", sorted(df["Class"].unique()))
            class_df = df[df["Class"] == selected_class]
            pivot_class = class_df.pivot(index="Period", columns="Day", values="Entry").reindex(columns=days_order).fillna("Free")
            st.dataframe(pivot_class, use_container_width=True)

            # Excel Export
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                pivot_class.to_excel(writer, sheet_name=selected_class)
            st.download_button(f"Export {selected_class} to Excel", data=buffer.getvalue(), file_name=f"{selected_class}_Timetable.xlsx", mime="application/vnd.ms-excel")

        with tab3:
            st.subheader("Teacher View")
            selected_teacher = st.selectbox("Select Teacher View", sorted(df["Teacher"].unique()))
            teacher_df = df[df["Teacher"] == selected_teacher]
            
            # Format display string for teacher
            teacher_df["Teacher_Entry"] = teacher_df["Subject"] + " (" + teacher_df["Class"] + ")"
            pivot_teacher = teacher_df.pivot(index="Period", columns="Day", values="Teacher_Entry").reindex(columns=days_order).fillna("Free")
            st.dataframe(pivot_teacher, use_container_width=True)

            # Excel Export
            buffer_t = io.BytesIO()
            with pd.ExcelWriter(buffer_t, engine='xlsxwriter') as writer:
                pivot_teacher.to_excel(writer, sheet_name=selected_teacher)
            st.download_button(f"Export {selected_teacher} Schedule to Excel", data=buffer_t.getvalue(), file_name=f"{selected_teacher}_Timetable.xlsx", mime="application/vnd.ms-excel")