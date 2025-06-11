import streamlit as st
from openai import OpenAI
import sqlite3
import datetime
import os

# Try to load from .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, that's fine

# Secure OpenAI client initialization
def get_openai_client():
    """Initialize OpenAI client with secure key management"""
    try:
        # Try multiple secure sources for API key
        api_key = None
        
        # 1. Streamlit secrets (recommended)
        if "OPENAI_API_KEY" in st.secrets:
            api_key = st.secrets["OPENAI_API_KEY"]
        # 2. Environment variables
        elif "OPENAI_API_KEY" in os.environ:
            api_key = os.environ["OPENAI_API_KEY"]
        
        if api_key and api_key.startswith("sk-"):
            return OpenAI(api_key=api_key)
        else:
            st.error("❌ OpenAI API key not found. Please configure your API key.")
            st.info("💡 See the setup instructions below.")
            return None
            
    except Exception as e:
        st.error(f"❌ Error connecting to OpenAI: {str(e)}")
        return None

# Initialize database
def init_db():
    conn = sqlite3.connect('stories.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS stories
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  title TEXT,
                  last_updated TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS sections
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  story_id INTEGER,
                  author TEXT,
                  content TEXT,
                  rating INTEGER,
                  created_at TIMESTAMP,
                  FOREIGN KEY(story_id) REFERENCES stories(id))''')
    conn.commit()
    conn.close()

# Helper functions
def get_stories():
    conn = sqlite3.connect('stories.db')
    c = conn.cursor()
    c.execute("SELECT id, title FROM stories ORDER BY last_updated DESC")
    stories = c.fetchall()
    conn.close()
    return stories

def create_story(title):
    conn = sqlite3.connect('stories.db')
    c = conn.cursor()
    c.execute("INSERT INTO stories (title, last_updated) VALUES (?, ?)",
              (title, datetime.datetime.now()))
    story_id = c.lastrowid
    conn.commit()
    conn.close()
    return story_id

def get_sections(story_id):
    conn = sqlite3.connect('stories.db')
    c = conn.cursor()
    c.execute("SELECT author, content, rating FROM sections WHERE story_id = ? ORDER BY created_at",
              (story_id,))
    sections = c.fetchall()
    conn.close()
    return sections

def add_section(story_id, author, content, rating=0):
    conn = sqlite3.connect('stories.db')
    c = conn.cursor()
    c.execute("INSERT INTO sections (story_id, author, content, rating, created_at) VALUES (?, ?, ?, ?, ?)",
              (story_id, author, content, rating, datetime.datetime.now()))
    # Update story last_updated timestamp
    c.execute("UPDATE stories SET last_updated = ? WHERE id = ?",
              (datetime.datetime.now(), story_id))
    conn.commit()
    conn.close()

def get_story_context(story_id, max_chars=2000):
    """Get recent story content for AI context"""
    sections = get_sections(story_id)
    context = ""
    for author, content, rating in reversed(sections[-5:]):  # Last 5 sections
        context = f"[{author}]: {content}\n\n" + context
        if len(context) > max_chars:
            break
    return context.strip()

def generate_ai_continuation(client, context, max_length=200):
    """Generate AI continuation using OpenAI"""
    try:
        with st.spinner("🤖 AI is writing the next part..."):
            response = client.chat.completions.create(
                model="gpt-4o-mini",  # Cost-effective model for story writing
                messages=[
                    {"role": "system", "content": "You are a creative writing assistant. Continue the story in a natural, engaging way. Keep it under 200 words and maintain the existing tone and style."},
                    {"role": "user", "content": f"Continue this story:\n\n{context}"}
                ],
                max_tokens=max_length,
                temperature=0.8
            )
            return response.choices[0].message.content.strip()
    except Exception as e:
        if "rate_limit" in str(e).lower():
            return "⏱️ Rate limit exceeded. Please wait a moment and try again."
        elif "quota" in str(e).lower():
            return "💳 API quota exceeded. Please check your OpenAI billing."
        else:
            return f"❌ Error generating AI continuation: {str(e)}"

# Initialize session state
def init_session_state():
    if 'story_id' not in st.session_state:
        st.session_state.story_id = None
    if 'sections' not in st.session_state:
        st.session_state.sections = []

# Main app
def main():
    st.title("📚 Interactive Story Writing Tool")
    
    # Initialize database and session state
    init_db()
    init_session_state()
    
    # Check OpenAI connection
    client = get_openai_client()
    
    if not client:
        st.warning("🔑 Please configure your OpenAI API key to enable AI features")
        
        with st.expander("🛠️ How to set up your API key", expanded=True):
            st.markdown("""
            **Method 1: Simple .env file (Easiest)**
            1. Create a file called `.env` in your project folder
            2. Add this line: `OPENAI_API_KEY=your-api-key-here`
            3. Install python-dotenv: `pip install python-dotenv`
            4. Restart the app
            
            **Method 2: Environment Variable**
            - Mac: `echo 'export OPENAI_API_KEY="your-key"' >> ~/.zshrc && source ~/.zshrc`
            - Windows: `setx OPENAI_API_KEY "your-api-key-here"`
            
            **Method 3: Streamlit Secrets**
            1. Create folder: `.streamlit` (use Terminal: `mkdir .streamlit`)
            2. Create file: `.streamlit/secrets.toml`
            3. Add: `OPENAI_API_KEY = "your-api-key-here"`
            
            **Get your API key from:** https://platform.openai.com/api-keys
            """)
            
            st.info("💡 Choose whichever method feels easiest for you!")
        
        st.info("💡 You can still use the collaborative writing features without AI!")
    
    # Story selection/creation
    stories = get_stories()
    story_options = ["New Story"] + [f"{s[1]} (ID: {s[0]})" for s in stories]
    selected_option = st.selectbox("Choose a story", story_options)
    
    if selected_option == "New Story":
        title = st.text_input("Enter a title for your new story")
        if title and st.button("Create Story"):
            story_id = create_story(title)
            st.session_state.story_id = story_id
            st.session_state.sections = []
            st.success(f"Created new story: {title}")
            st.rerun()
    else:
        story_id = int(selected_option.split("ID: ")[1].rstrip(")"))
        st.session_state.story_id = story_id
        st.session_state.sections = get_sections(story_id)
    
    # Display current story
    if st.session_state.story_id:
        st.header("📖 Current Story")
        
        # Display all sections
        if st.session_state.sections:
            for i, (author, content, rating) in enumerate(st.session_state.sections):
                with st.container():
                    st.markdown(f"**Section {i+1} by {author}** ⭐ Rating: {rating}")
                    st.markdown(f"*{content}*")
                    st.divider()
        else:
            st.info("👋 This story is just beginning! Add the first section below.")
        
        # Get AI Continuation (only if client is available)
        if client:
            st.header("🤖 Get AI Continuation")
            if st.button("Generate AI Continuation", type="secondary"):
                context = get_story_context(st.session_state.story_id)
                if context:
                    ai_content = generate_ai_continuation(client, context)
                    add_section(st.session_state.story_id, "AI Assistant", ai_content)
                    st.session_state.sections = get_sections(st.session_state.story_id)
                    st.success("🎉 AI continuation added!")
                    st.rerun()
                else:
                    st.warning("📝 Start the story first, then I can continue it!")
        
        # Submit Your Section
        st.header("✍️ Add Your Section")
        with st.form("new_section"):
            author_name = st.text_input("Your name", placeholder="Enter your name")
            section_content = st.text_area("Write your section", height=150, 
                                         placeholder="Continue the story here...")
            col1, col2 = st.columns([3, 1])
            with col1:
                submitted = st.form_submit_button("Submit Section", type="primary")
            
            if submitted and author_name and section_content:
                add_section(st.session_state.story_id, author_name, section_content)
                st.session_state.sections = get_sections(st.session_state.story_id)
                st.success(f"📝 Section by {author_name} added!")
                st.rerun()
            elif submitted:
                st.error("⚠️ Please fill in both your name and story content.")
    
    # Instructions
    with st.sidebar:
        st.header("📋 How to use")
        st.markdown("""
        1. **Create** a new story or select existing
        2. **Read** current story sections  
        3. **Write** your own section OR
        4. **Generate** AI continuation
        5. **Collaborate** and build together!
        
        ---
        
        💡 **Tips:**
        - Keep sections 1-3 paragraphs
        - Maintain story continuity
        - Have fun with creativity!
        """)
        
        if client:
            st.success("✅ AI features enabled")
        else:
            st.warning("⚠️ AI features disabled")
            st.caption("Configure API key to enable")

if __name__ == "__main__":
    main()