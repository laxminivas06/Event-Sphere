from fpdf import FPDF
import os
import json

class DocumentationPDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.set_text_color(30, 40, 100)
        self.cell(0, 10, 'SphoorthyEventSphere - Master Technical Dossier', 0, 1, 'C')
        self.set_draw_color(100, 100, 150)
        self.line(10, 22, 200, 22)
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128)
        self.cell(0, 10, f'Confidential - Developer Resource - Page {self.page_no()}', 0, 0, 'C')

    def section_title(self, title):
        self.set_font('Arial', 'B', 16)
        self.set_fill_color(220, 230, 255)
        self.set_text_color(20, 30, 80)
        self.cell(0, 12, f'  {title}', 0, 1, 'L', 1)
        self.ln(5)

    def sub_section_title(self, title):
        self.set_font('Arial', 'B', 13)
        self.set_text_color(40, 50, 120)
        self.cell(0, 10, title, 0, 1, 'L')
        self.ln(2)

    def content_para(self, text):
        self.set_font('Arial', '', 11)
        self.set_text_color(40, 40, 40)
        self.multi_cell(0, 6, text)
        self.ln(4)

    def code_box(self, code):
        self.set_font('Courier', '', 9)
        self.set_fill_color(248, 248, 250)
        self.set_text_color(50, 50, 50)
        self.multi_cell(0, 5, code, 1, 'L', 1)
        self.ln(5)

    def file_list(self, files):
        self.set_font('Arial', 'B', 10)
        self.set_text_color(60, 60, 60)
        for f in files:
            self.bullet_point(f)
        self.ln(3)

    def bullet_point(self, text):
        self.set_font('Arial', '', 10)
        self.set_text_color(40, 40, 40)
        self.cell(10, 6, '-', 0, 0, 'C')
        self.multi_cell(0, 6, text)

def generate_master_dossier(output_path):
    pdf = DocumentationPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # --- PAGE 1: INTRODUCTION & VISION ---
    pdf.section_title('1. Executive Introduction')
    pdf.content_para(
        "SphoorthyEventSphere is a high-performance, enterprise-grade digital ecosystem designed to unify campus engagement. "
        "The platform transcends traditional management systems by integrating financial accountability, administrative oversight, "
        "and student-centric interaction into a single, cohesive experience. "
        "\n\nIn a modern educational environment, data is the most valuable asset. This system ensures that every event - from a small "
        "club meeting to a massive 48-hour hackathon - is captured, analyzed, and archived with precision. The design philosophy centers "
        "on 'Visual Excellence and Functional Simplicity', utilizing cutting-edge web technologies to deliver a premium user experience."
    )
    pdf.sub_section_title('1.1 Core Mission')
    pdf.content_para(
        "To empower student leaders with the tools of professional management while providing institutional heads with "
        "real-time transparency into campus activities and financial health."
    )
    pdf.sub_section_title('1.2 Key Differentiators')
    pdf.bullet_point("Zero-DB Maintenance: Utilizing a high-speed JSON flat-file system for instant deployment and portability.")
    pdf.bullet_point("Role-Specific Intelligence: Tailored dashboards for 6 distinct personas including Evaluators and Super Admins.")
    pdf.bullet_point("Integrated Financial Pipeline: Automated revenue splitting for collaborative events and locked expense reporting.")

    # --- PAGE 2: BACKEND ARCHITECTURE (PYTHON) ---
    pdf.add_page()
    pdf.section_title('2. Backend Architecture: Python Ecosystem')
    pdf.content_para(
        "The backend is built using the Flask micro-framework, chosen for its modularity and speed. The system is split into "
        "blueprints to separate core routing from specialized event management modules."
    )
    
    pdf.sub_section_title('2.1 Core Backend Files')
    pdf.bullet_point("run.py: The entry point of the application. It initializes the Flask instance and configures the host/port.")
    pdf.bullet_point("app/__init__.py: Central initialization. Defines the app factory, registers blueprints (api, em), and sets up session management.")
    pdf.bullet_point("app/models.py: The Data Access Object (DAO) layer. Contains the 'DB' class which abstracts all file-based operations.")
    pdf.bullet_point("app/routes.py: Primary API and view logic for students and general administration.")
    pdf.bullet_point("app/event_mgmt_routes.py: The most complex logic file, handling ticketing, QR generation, and Razorpay verification.")
    pdf.bullet_point("app/mailer.py: Integration with SMTP servers to send tickets and verification emails with attachments.")

    pdf.sub_section_title('2.2 Logic Deep Dive: The DB Class')
    pdf.content_para(
        "The DB class in models.py uses the 'json' and 'os' libraries to simulate a database. It ensures thread-safe operations "
        "by utilizing scoped directory structures. For example, 'get_events(club_id)' dynamically scans only the subdirectories "
        "relevant to that club, ensuring O(log N) performance for data retrieval."
    )

    # --- PAGE 3: DATABASE & FILE FORMATS ---
    pdf.add_page()
    pdf.section_title('3. Database Formats & Persistence')
    pdf.content_para(
        "The system rejects the complexity of SQL in favor of a human-readable, highly portable JSON structure. "
        "All data resides in the '/data' root directory, partitioned by module."
    )

    pdf.sub_section_title('3.1 Schema: Student Identity')
    pdf.content_para("Every student is a node in the 'students.json' array. Key attributes include:")
    pdf.code_box(
        "{\n"
        "  'roll_number': 'String (Primary Key)',\n"
        "  'name': 'String',\n"
        "  'department': 'String',\n"
        "  'year': 'Integer',\n"
        "  'dob': 'YYYY-MM-DD',\n"
        "  'contributions': 'Array<EventID>'\n"
        "}"
    )

    pdf.sub_section_title('3.2 Schema: Club & Event Hierarchy')
    pdf.content_para(
        "Clubs are stored as directories. Inside each club directory, a 'slug' folder exists for every event. "
        "This ensures that attachments (posters, reports) are co-located with their metadata (info.json)."
    )
    pdf.bullet_point("Path: /data/clubs/{club_id}/{event_title_slug}/")
    pdf.bullet_point("info.json: Core event configuration (fee, date, venue).")
    pdf.bullet_point("registrations.json: List of all students who signed up for this specific event.")

    # --- PAGE 4: TEMPLATE ARCHITECTURE (HTML) ---
    pdf.add_page()
    pdf.section_title('4. Frontend: Template Architecture')
    pdf.content_para(
        "The frontend uses Jinja2 templating, allowing for dynamic content injection while maintaining a clean separation "
        "of concerns. There are 81+ templates categorized by role and function."
    )

    pdf.sub_section_title('4.1 Global Layouts')
    pdf.bullet_point("layout.html: The master wrapper. Contains the head, navigation, and footer.")
    pdf.bullet_point("login.html / register.html: Entry points for the ecosystem.")
    pdf.bullet_point("index.html: The immersive landing page with dynamic event carousels.")

    pdf.sub_section_title('4.2 Super Admin Templates (Full Control)')
    pdf.bullet_point("admin_super.html: The central command center showing global metrics.")
    pdf.bullet_point("super_master_db.html: Interface for searching and bulk-updating the student registry.")
    pdf.bullet_point("super_approvals.html: The gatekeeper view for event permission letters.")
    pdf.bullet_point("super_settings.html: Configuration for institution-wide API keys.")

    pdf.sub_section_title('4.3 Club Admin Templates (Operation Focused)')
    pdf.bullet_point("admin_club.html: The club-specific dashboard.")
    pdf.bullet_point("admin_club_identity.html: Controls for Mission, Vision, and Club Gallery.")
    pdf.bullet_point("admin_event_setup.html: Wizard-style interface for creating complex events.")
    pdf.bullet_point("admin_club_finance.html: Detailed ledger of club income vs expenditure.")

    # --- PAGE 5: EVENT MANAGEMENT SYSTEM (EM) TEMPLATES ---
    pdf.add_page()
    pdf.section_title('5. Specialized Module Templates')
    pdf.content_para(
        "The EM (Event Management) and specialized tech fest modules require highly interactive interfaces "
        "for real-time data handling."
    )

    pdf.sub_section_title('5.1 Ticketing & Scanner (The EM Suite)')
    pdf.bullet_point("em_admin.html: A massive dashboard (95KB+) handling multi-club ticketing stats.")
    pdf.bullet_point("em_event_hub.html: Control center for a single event (Analytics, Bulk Email, etc.).")
    pdf.bullet_point("em_scanner.html: The camera-integrated QR code scanning interface.")
    pdf.bullet_point("em_ticket.html: The user-facing ticket view with interactive QR codes.")

    pdf.sub_section_title('5.2 Tech Fest & Hackathon Specifics')
    pdf.bullet_point("em_techfest_landing.html: High-visual-impact landing page for tech festivals.")
    pdf.bullet_point("em_hackathon_teams.html: Interface for leaderboards and team management.")
    pdf.bullet_point("evaluator_dashboard.html: Secure, search-optimized interface for competition grading.")
    pdf.bullet_point("em_hackathon_project_submit.html: Submission portal for hackathon source code/projects.")

    # --- PAGE 6: DESIGN PHILOSOPHY & CSS ---
    pdf.add_page()
    pdf.section_title('6. Design Philosophy: Visual Excellence')
    pdf.content_para(
        "The design is not just an afterthought; it is a core feature. We utilize modern UI trends to create "
        "an environment that feels premium and state-of-the-art."
    )

    pdf.sub_section_title('6.1 Aesthetic Principles')
    pdf.bullet_point("Glassmorphism: Using 'backdrop-filter: blur' and semi-transparent layers for a modern look.")
    pdf.bullet_point("Dynamic Gradients: Harmonious HSL-based colors (Indigo, Violet, Slate) to guide user focus.")
    pdf.bullet_point("Micro-Animations: Hover states and smooth transitions for interactive elements.")

    pdf.sub_section_title('6.2 CSS Architecture')
    pdf.content_para(
        "We avoid heavy frameworks like Tailwind in favor of curated Vanilla CSS. This ensures zero bloat "
        "and total control over the responsive grid system."
    )
    pdf.code_box(
        "/* Example: The Glass Dashboard Card */\n"
        ".card {\n"
        "  background: rgba(255, 255, 255, 0.03);\n"
        "  border: 1px solid rgba(255, 255, 255, 0.1);\n"
        "  backdrop-filter: blur(12px);\n"
        "  border-radius: 16px;\n"
        "  transition: transform 0.3s ease;\n"
        "}"
    )

    # --- PAGE 7: FINANCIAL & REPORTING LOGIC ---
    pdf.add_page()
    pdf.section_title('7. Financial Transparency & Reporting')
    pdf.content_para(
        "One of the system's most critical features is the Financial Hub, which ensures absolute "
        "accountability for every event budget."
    )

    pdf.sub_section_title('7.1 The Report Generator')
    pdf.bullet_point("report_generator.html: A sophisticated tool that compiles event data into a professional PDF.")
    pdf.bullet_point("Automated Data Points: Attendance percentage, Revenue totals, and Expenditure breakdown.")
    pdf.bullet_point("Approval Workflow: Reports must be uploaded and then verified by the Super Admin.")

    pdf.sub_section_title('7.2 Finance Locking Mechanism')
    pdf.content_para(
        "To prevent retroactive data tampering, the system 'locks' an event's finance once a report is submitted. "
        "Any further edits require a formal 'Unlock Request' to the Super Admin, documented in the system audit trail."
    )

    # --- PAGE 8: SECURITY & SCALABILITY ---
    pdf.add_page()
    pdf.section_title('8. Security & Data Integrity')
    pdf.content_para(
        "Operating without a traditional SQL database requires robust security measures at the application layer."
    )

    pdf.sub_section_title('8.1 Role-Based Access Control (RBAC)')
    pdf.content_para(
        "Access is strictly enforced in the routes. Every administrative request checks the session['user']['role'] "
        "against the required permission. For example, only roles with the 'super_admin' tag can access the /admin/super/ routes."
    )

    pdf.sub_section_title('8.2 Payment Security')
    pdf.bullet_point("Webhook-style Verification: We use Razorpay's signature verification to ensure the client-side hasn't forged the success call.")
    pdf.bullet_point("Unique Identifiers: Every registration has a UUID combined with a human-readable Ticket ID.")

    # --- PAGE 9: DEVELOPER EXTENSIBILITY ---
    pdf.add_page()
    pdf.section_title('9. Developer Extensibility Guide')
    pdf.content_para(
        "The system is designed to be modular. A developer can add a new club or a new event category by simply "
        "adding a new entry to the configuration files and creating the corresponding template."
    )

    pdf.sub_section_title('9.1 Adding a New Module')
    pdf.bullet_point("1. Define a new Blueprint in the 'app/' directory.")
    pdf.bullet_point("2. Create a specific directory in '/templates' for the module.")
    pdf.bullet_point("3. Add the necessary logic to models.py for data persistence.")

    pdf.sub_section_title('9.2 Best Practices for Maintainers')
    pdf.bullet_point("Always validate JSON structures before saving to avoid file corruption.")
    pdf.bullet_point("Maintain the HSL color palette in CSS for all new UI components.")
    pdf.bullet_point("Ensure all new routes have a corresponding role check.")

    # --- PAGE 10: CONCLUSION & FUTURE VISION ---
    pdf.add_page()
    pdf.section_title('10. Conclusion & Future Outlook')
    pdf.content_para(
        "SphoorthyEventSphere is more than just a software tool; it is a digital backbone for campus life. "
        "By consolidating all aspects of event management into a high-performance, visually stunning platform, "
        "we have set a new standard for educational administration."
    )
    
    pdf.sub_section_title('10.1 Future Roadmap')
    pdf.bullet_point("AI-Powered Analytics: Predicting event turnout based on historical student participation data.")
    pdf.bullet_point("Mobile Companion App: Native iOS/Android apps for faster attendance scanning via specialized hardware.")
    pdf.bullet_point("Institutional API: Allowing other college systems to securely query the student history database.")

    pdf.content_para(
        "As the ecosystem grows, the focus remains on maintaining the speed and simplicity that the JSON-based "
        "architecture provides, while continuing to push the boundaries of modern web design."
    )

    pdf.output(output_path)

if __name__ == "__main__":
    output_file = "/Users/nivas/Documents/Python Softwarez/SphoorthyEventSphere/SphoorthyEventSphere_Master_Technical_Dossier.pdf"
    generate_master_dossier(output_file)
    print(f"Master Technical Dossier generated: {output_file}")
