import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for
from openai import OpenAI

app = Flask(__name__)
DATABASE = "job_diary.db"


# ==========================================
# 0. DB 연결 및 초기화 공통 함수, 초안
# ==========================================
def get_db():
    """데이터베이스 연결 객체를 생성하고 컬럼명 접근(Row)을 설정합니다."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """앱 실행 시 테이블이 없으면 자동 생성하는 함수 (README 및 각 파트 스키마 통합)"""
    with get_db() as conn:

        # 1. memos (글로벌 퀵 메모)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                page_index TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 2. todos (할 일 및 일정)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                due_date TEXT,
                is_done INTEGER DEFAULT 0,
                repeat_type TEXT DEFAULT 'none',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 3. resume_profiles (HISTORY 파트: 기본 인적사항)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS resume_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                birth_date TEXT,
                phone TEXT,
                email TEXT,
                address TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 4. educations (HISTORY 파트: 학력)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS educations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                school_type TEXT,
                school_name TEXT,
                major TEXT,
                start_date TEXT,
                end_date TEXT,
                grade TEXT
            )
        """)

        # 5. careers (경력)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS careers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT,
                department TEXT,
                position TEXT,
                start_date TEXT,
                end_date TEXT,
                responsibilities TEXT,
                achievements TEXT
            )
        """)

        # 6. certificates (자격증)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS certificates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                certificate_name TEXT,
                issuer TEXT,
                acquired_date TEXT
            )
        """)

        # 7. languages (어학)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS languages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_name TEXT,
                score TEXT,
                acquired_date TEXT
            )
        """)

        # 8. activities (프로젝트 / 대외활동)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activity_name TEXT,
                organization TEXT,
                start_date TEXT,
                end_date TEXT,
                role TEXT,
                content TEXT,
                achievement TEXT
            )
        """)

        # 9. reviews (내용 복기)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT,
                position TEXT,
                apply_date TEXT,
                review_type TEXT,
                result TEXT,
                interview_date TEXT,
                question TEXT,
                answer TEXT,
                submitted_content TEXT,
                feedback TEXT,
                keep_point TEXT,
                problem_point TEXT,
                try_point TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 10. jobs (채용공고)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT,
                job_title TEXT,
                position TEXT,
                job_category TEXT,
                location TEXT,
                job_url TEXT,
                posted_date TEXT,
                deadline TEXT,
                status TEXT DEFAULT '관심',
                is_favorite INTEGER DEFAULT 0,
                memo TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()


# 서버 시작 전 DB 테이블 초기화 실행
init_db()


def render_or_placeholder(template_name, page_index, title_text):
    """
    팀원이 아직 템플릿 파일을 완성하지 않았거나 없을 때
    서버 에러(TemplateNotFound) 없이 안내 화면을 띄워주는 안전 렌더러 함수입니다.
    """
    template_path = os.path.join(app.template_folder, template_name)

    if os.path.exists(template_path):
        return render_template(
            template_name,
            page_index=page_index
        )

    placeholder_html = f"""
    {{% extends "base.html" %}}
    {{% block content %}}
    <section class="bg-white/80 p-6 rounded-xl border border-stone-200 shadow-sm text-center">
        <h2 class="text-lg font-bold text-stone-700 mb-2">🚧 {title_text}</h2>
        <p class="text-sm text-stone-500 mb-4">
            현재 담당 팀원이 <code>templates/{template_name}</code>을 작업 중입니다.
        </p>
        <span class="inline-block text-xs bg-amber-100 text-amber-800 px-3 py-1 rounded-full font-semibold">
            식별 코드: [{page_index}]
        </span>
    </section>
    {{% endblock %}}
    """

    from flask import render_template_string

    return render_template_string(
        placeholder_html,
        page_index=page_index
    )


# ==========================================
# 00. 메인 화면 (HOME) - 본인 파트
# ==========================================
@app.route("/")
def home():
    """메인 대시보드 화면: 취준 현황 요약, 오늘의 TODO 목록 제공"""

    today_str = datetime.today().strftime("%Y.%m.%d")

    todo_count = 0
    saved_jobs_count = 0
    upcoming_deadline_count = 0
    today_todos = []

    try:
        with get_db() as conn:

            # 1) TODO 미완료 개수
            todo_row = conn.execute(
                "SELECT COUNT(*) FROM todos WHERE is_done = 0"
            ).fetchone()

            todo_count = todo_row[0] if todo_row else 0

            # 2) 저장된 채용공고 총 개수
            jobs_row = conn.execute(
                "SELECT COUNT(*) FROM jobs"
            ).fetchone()

            saved_jobs_count = jobs_row[0] if jobs_row else 0

            # 3) 다가오는 마감(D-Day 7일 이내)
            deadline_row = conn.execute(
                """
                SELECT COUNT(*)
                FROM jobs
                WHERE deadline >= date('now')
                AND deadline <= date('now', '+7 days')
                """
            ).fetchone()

            upcoming_deadline_count = (
                deadline_row[0]
                if deadline_row
                else 0
            )

            # 4) 오늘의 TODO 목록
            today_todos = conn.execute(
                """
                SELECT *
                FROM todos
                WHERE due_date = date('now')
                LIMIT 5
                """
            ).fetchall()

    except sqlite3.OperationalError:
        init_db()

    # 등록된 할 일이 없을 때 보여줄 기본 예시 데이터
    if not today_todos:
        today_todos = [
            {
                "id": 1,
                "title": "자기소개서 작성",
                "is_done": 0
            },
            {
                "id": 2,
                "title": "기업 분석",
                "is_done": 0
            },
            {
                "id": 3,
                "title": "채용공고 확인",
                "is_done": 0
            }
        ]

    summary = {
        "todo_count": todo_count if todo_count > 0 else 3,
        "saved_jobs_count": (
            saved_jobs_count
            if saved_jobs_count > 0
            else 8
        ),
        "upcoming_deadline_count": (
            upcoming_deadline_count
            if upcoming_deadline_count > 0
            else 2
        )
    }

    return render_template(
        "index.html",
        page_index="00 HOME",
        today_date=today_str,
        summary=summary,
        today_todos=today_todos
    )


# ==========================================
# 02. HISTORY / 이력관리 - [HISTORY 팀원 파트 반영]
# ==========================================
@app.route("/history")
def history():
    """HISTORY 메인 화면: DB에서 데이터를 불러와 화면에 전달"""

    with get_db() as conn:
        profile = conn.execute(
            """
            SELECT *
            FROM resume_profiles
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

        educations = conn.execute(
            """
            SELECT *
            FROM educations
            ORDER BY id DESC
            """
        ).fetchall()

    template_path = os.path.join(
        app.template_folder,
        "history.html"
    )

    if os.path.exists(template_path):
        return render_template(
            "history.html",
            profile=profile,
            educations=educations,
            page_index="02 HISTORY"
        )

    return render_or_placeholder(
        "history.html",
        "02 HISTORY",
        "02 HISTORY / 이력관리"
    )


@app.route("/history/profile", methods=["POST"])
def save_profile():
    """기본정보 폼 제출 시 DB에 저장"""

    name = request.form.get("name")
    birth_date = request.form.get("birth_date")
    phone = request.form.get("phone")
    email = request.form.get("email")
    address = request.form.get("address")

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO resume_profiles (
                name,
                birth_date,
                phone,
                email,
                address
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                name,
                birth_date,
                phone,
                email,
                address
            )
        )

        conn.commit()

    return redirect(url_for("history"))


@app.route("/history/education", methods=["POST"])
def add_education():
    """학력 폼 제출 시 DB에 추가"""

    school_type = request.form.get("school_type")
    school_name = request.form.get("school_name")
    major = request.form.get("major")
    grade = request.form.get("grade")
    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO educations (
                school_type,
                school_name,
                major,
                grade,
                start_date,
                end_date
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                school_type,
                school_name,
                major,
                grade,
                start_date,
                end_date
            )
        )

        conn.commit()

    return redirect(url_for("history"))


# ==========================================
# 01, 03, 04, 05. 서브 기능 라우트
# ==========================================
@app.route("/calendar")
def calendar():
    """01 TODO / CALENDAR 담당 팀원 브랜치 연동 영역"""

    return render_or_placeholder(
        "calendar.html",
        "01 TODO",
        "01 TODO / CALENDAR"
    )


@app.route("/review")
def review():
    """03 REVIEW 담당 팀원 브랜치 연동 영역"""

    return render_or_placeholder(
        "review.html",
        "03 REVIEW",
        "03 REVIEW / 내용복기"
    )


# ==========================================
# [04 JOBS 수정]
# 채용공고 등록(Create) + 목록 조회(Read)
# ==========================================
@app.route("/jobs", methods=["GET", "POST"])
def jobs():
    """04 JOBS - 채용공고 등록 및 목록 조회"""

    # 공고 등록 요청
    if request.method == "POST":

        company_name = request.form.get("company_name")
        job_title = request.form.get("job_title")
        position = request.form.get("position")
        job_category = request.form.get("job_category")
        location = request.form.get("location")
        job_url = request.form.get("job_url")
        posted_date = request.form.get("posted_date")
        deadline = request.form.get("deadline")
        status = request.form.get("status", "관심")
        memo = request.form.get("memo")

        # 체크박스가 선택되면 1, 아니면 0
        is_favorite = (
            1
            if request.form.get("is_favorite")
            else 0
        )

        with get_db() as conn:

            conn.execute(
                """
                INSERT INTO jobs (
                    company_name,
                    job_title,
                    position,
                    job_category,
                    location,
                    job_url,
                    posted_date,
                    deadline,
                    status,
                    is_favorite,
                    memo
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company_name,
                    job_title,
                    position,
                    job_category,
                    location,
                    job_url,
                    posted_date,
                    deadline,
                    status,
                    is_favorite,
                    memo
                )
            )

            conn.commit()

        # 새로고침 시 중복 등록되는 것을 막기 위해 redirect
        return redirect(
            url_for("jobs")
        )

    # 저장된 채용공고 목록 조회
    with get_db() as conn:

        job_list = conn.execute(
            """
            SELECT *
            FROM jobs
            ORDER BY created_at DESC
            """
        ).fetchall()

    return render_template(
        "jobs.html",
        jobs=job_list,
        page_index="04 JOBS"
    )


@app.route("/ai")
def ai():
    """05 AI 담당 팀원 브랜치 연동 영역"""

    return render_or_placeholder(
        "ai.html",
        "05 AI",
        "05 AI / AI 도우미"
    )


# ==========================================
# 05 AI / 취업용 Prompt Generator API
# ==========================================
@app.route("/api/generate-prompt", methods=["POST"])
def generate_prompt():
    """사용자의 요청을 바탕으로 취업용 완성형 프롬프트를 생성합니다."""

    data = request.get_json()

    if not data:
        return jsonify({
            "success": False,
            "message": "요청 데이터가 없습니다."
        }), 400

    api_key = data.get(
        "api_key",
        ""
    ).strip()

    prompt_type = data.get(
        "prompt_type",
        ""
    ).strip()

    user_request = data.get(
        "user_request",
        ""
    ).strip()

    if not api_key:
        return jsonify({
            "success": False,
            "message": "OpenAI API Key를 입력해주세요."
        }), 400

    if not prompt_type:
        return jsonify({
            "success": False,
            "message": "프롬프트 유형을 선택해주세요."
        }), 400

    if not user_request:
        return jsonify({
            "success": False,
            "message": "취업 준비 내용을 입력해주세요."
        }), 400

    prompt_type_names = {
        "cover_letter": "자기소개서 작성",
        "cover_letter_review": "자기소개서 첨삭",
        "company_analysis": "기업분석",
        "job_analysis": "직무분석",
        "interview_questions": "면접 예상질문",
        "star_answer": "STAR 답변",
        "follow_up": "면접 꼬리질문"
    }

    prompt_type_name = prompt_type_names.get(
        prompt_type
    )

    if not prompt_type_name:
        return jsonify({
            "success": False,
            "message": "올바르지 않은 프롬프트 유형입니다."
        }), 400

    system_instruction = """
당신은 취업용 Prompt Generator입니다.

사용자의 취업 준비 결과물을 직접 대신 작성하지 말고,
사용자가 ChatGPT 또는 Gemini에 복사해서 사용할 수 있는
완성형 프롬프트를 생성해야 합니다.

생성하는 프롬프트에는 가능한 경우 다음 내용을 포함하세요.

1. AI가 수행할 역할
2. 지원 기업
3. 지원 직무
4. 사용자가 제공한 경험과 정보
5. 수행할 작업
6. 출력 형식
7. 작성 조건
8. 확인되지 않은 정보를 만들지 말라는 조건
9. 정보가 부족하면 추가 질문을 하라는 조건

사용자가 제공하지 않은 경험, 성과, 숫자 또는 사실은
임의로 만들어내지 마세요.

설명이나 인사말 없이
사용자가 바로 복사해서 사용할 수 있는
프롬프트만 출력하세요.
""".strip()

    generation_request = f"""
프롬프트 유형:
{prompt_type_name}

사용자의 취업 준비 내용:
{user_request}

위 정보를 바탕으로
'{prompt_type_name}' 작업에 사용할 수 있는
완성형 취업 프롬프트를 만들어주세요.

사용자는 생성된 프롬프트를
ChatGPT 또는 Gemini에 그대로 복사해서 사용할 예정입니다.
""".strip()

    try:
        # 사용자가 입력한 API Key는 이 요청에서만 사용합니다.
        # DB나 파일에는 저장하지 않습니다.
        client = OpenAI(
            api_key=api_key
        )

        response = client.responses.create(
            model="gpt-4.1-mini",
            instructions=system_instruction,
            input=generation_request
        )

        generated_prompt = (
            response.output_text or ""
        ).strip()

        if not generated_prompt:
            return jsonify({
                "success": False,
                "message": "생성된 프롬프트가 없습니다."
            }), 500

        return jsonify({
            "success": True,
            "prompt": generated_prompt
        })

    except Exception as error:
        # API Key 자체는 로그에 출력하지 않습니다.
        print(
            "OpenAI API 호출 오류:",
            type(error).__name__
        )

        return jsonify({
            "success": False,
            "message":
                "OpenAI API 호출에 실패했습니다. "
                "API Key 또는 API 사용 상태를 확인해주세요."
        }), 500


# ==========================================
# 공통 API: 글로벌 퀵 메모 저장
# ==========================================
@app.route("/api/memos", methods=["POST"])
def save_quick_memo():
    """모든 페이지에서 호출하는 글로벌 퀵 메모 저장 엔드포인트"""

    data = (
        request.get_json()
        if request.is_json
        else request.form
    )

    page_index = data.get(
        "page_index",
        "00 HOME"
    )

    content = data.get(
        "content",
        ""
    ).strip()

    if not content:
        return jsonify({
            "success": False,
            "message": "내용을 입력해주세요."
        }), 400

    with get_db() as conn:

        conn.execute(
            """
            INSERT INTO memos (
                page_index,
                content
            )
            VALUES (?, ?)
            """,
            (
                page_index,
                content
            )
        )

        conn.commit()

    return jsonify({
        "success": True,
        "message": "메모가 성공적으로 저장되었습니다."
    })


if __name__ == "__main__":
    init_db()
    app.run(
        debug=True,
        port=5000
    )