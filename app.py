import streamlit as st
from openai import OpenAI
import sqlite3
import datetime
import os
import json

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
            st.info("💡 See the setup instructions in the sidebar.")
            return None
            
    except Exception as e:
        st.error(f"❌ Error connecting to OpenAI: {str(e)}")
        return None

# Initialize database with enhanced schema
def init_db():
    conn = sqlite3.connect('writing_sessions.db')
    c = conn.cursor()
    
    # Stories table
    c.execute('''CREATE TABLE IF NOT EXISTS stories
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  title TEXT,
                  user_text TEXT,
                  created_at TIMESTAMP,
                  last_updated TIMESTAMP)''')
    
    # Chapters table with ratings and style
    c.execute('''CREATE TABLE IF NOT EXISTS chapters
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  story_id INTEGER,
                  chapter_number INTEGER,
                  user_content TEXT,
                  ai_content TEXT,
                  ai_style TEXT,
                  user_rating INTEGER,
                  ai_rating INTEGER,
                  created_at TIMESTAMP,
                  FOREIGN KEY(story_id) REFERENCES stories(id))''')
    
    # Polish sessions table
    c.execute('''CREATE TABLE IF NOT EXISTS polish_sessions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  story_id INTEGER,
                  original_text TEXT,
                  polished_text TEXT,
                  ai_rating INTEGER,
                  user_rating INTEGER,
                  feedback TEXT,
                  created_at TIMESTAMP,
                  FOREIGN KEY(story_id) REFERENCES stories(id))''')
    
    conn.commit()
    conn.close()

# Database helper functions
def create_story(title, user_text):
    conn = sqlite3.connect('writing_sessions.db')
    c = conn.cursor()
    c.execute("INSERT INTO stories (title, user_text, created_at, last_updated) VALUES (?, ?, ?, ?)",
              (title, user_text, datetime.datetime.now(), datetime.datetime.now()))
    story_id = c.lastrowid
    conn.commit()
    conn.close()
    return story_id

def get_stories():
    conn = sqlite3.connect('writing_sessions.db')
    c = conn.cursor()
    c.execute("SELECT id, title, created_at FROM stories ORDER BY last_updated DESC")
    stories = c.fetchall()
    conn.close()
    return stories

def get_story_details(story_id):
    conn = sqlite3.connect('writing_sessions.db')
    c = conn.cursor()
    c.execute("SELECT title, user_text FROM stories WHERE id = ?", (story_id,))
    result = c.fetchone()
    conn.close()
    return result

def get_chapters(story_id):
    conn = sqlite3.connect('writing_sessions.db')
    c = conn.cursor()
    c.execute("SELECT chapter_number, user_content, ai_content, ai_style, user_rating, ai_rating FROM chapters WHERE story_id = ? ORDER BY chapter_number", (story_id,))
    chapters = c.fetchall()
    conn.close()
    return chapters

def add_chapter(story_id, chapter_number, user_content, ai_content, ai_style, ai_rating):
    conn = sqlite3.connect('writing_sessions.db')
    c = conn.cursor()
    c.execute("INSERT INTO chapters (story_id, chapter_number, user_content, ai_content, ai_style, ai_rating, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (story_id, chapter_number, user_content, ai_content, ai_style, ai_rating, datetime.datetime.now()))
    conn.commit()
    conn.close()

def update_chapter_rating(story_id, chapter_number, user_rating):
    conn = sqlite3.connect('writing_sessions.db')
    c = conn.cursor()
    c.execute("UPDATE chapters SET user_rating = ? WHERE story_id = ? AND chapter_number = ?",
              (user_rating, story_id, chapter_number))
    conn.commit()
    conn.close()

def add_polish_session(story_id, original_text, polished_text, ai_rating):
    conn = sqlite3.connect('writing_sessions.db')
    c = conn.cursor()
    c.execute("INSERT INTO polish_sessions (story_id, original_text, polished_text, ai_rating, created_at) VALUES (?, ?, ?, ?, ?)",
              (story_id, original_text, polished_text, ai_rating, datetime.datetime.now()))
    session_id = c.lastrowid
    conn.commit()
    conn.close()
    return session_id

def update_polish_rating(session_id, user_rating, feedback):
    conn = sqlite3.connect('writing_sessions.db')
    c = conn.cursor()
    c.execute("UPDATE polish_sessions SET user_rating = ?, feedback = ? WHERE id = ?",
              (user_rating, feedback, session_id))
    conn.commit()
    conn.close()

def get_user_rating_history(story_id):
    """Get user's rating history to help AI improve"""
    conn = sqlite3.connect('writing_sessions.db')
    c = conn.cursor()
    c.execute("SELECT user_rating, feedback FROM polish_sessions WHERE story_id = ? AND user_rating IS NOT NULL ORDER BY created_at DESC LIMIT 5", (story_id,))
    ratings = c.fetchall()
    conn.close()
    return ratings

# AI Generation Functions
def generate_next_chapter(client, story_context, user_chapter, style_direction, previous_ratings):
    """Generate next chapter based on user's writing and style direction"""
    try:
        # Build context based on previous ratings
        rating_context = ""
        if previous_ratings:
            avg_rating = sum([r[0] for r in previous_ratings if r[0]]) / len([r for r in previous_ratings if r[0]])
            if avg_rating < 3:
                rating_context = "The user has given lower ratings recently, so focus on being more engaging and creative. "
            elif avg_rating >= 4:
                rating_context = "The user has been happy with previous content, maintain this quality level. "
        
        system_prompt = f"""You are a creative writing assistant helping to continue a story. 
        {rating_context}
        
        Style direction: {style_direction}
        
        Rules:
        1. Continue the story naturally from where the user left off
        2. Match the tone and style of the existing story
        3. Apply the style direction: {style_direction}
        4. Keep chapters engaging and well-paced
        5. End with a compelling hook for the next chapter
        6. Write 200-400 words
        """
        
        user_prompt = f"""Story context: {story_context}

User's latest chapter: {user_chapter}

Continue this story with the style: {style_direction}"""

        with st.spinner(f"🎭 Creating a {style_direction} continuation..."):
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=600,
                temperature=0.8
            )
            return response.choices[0].message.content.strip()
    
    except Exception as e:
        return f"❌ Error generating chapter: {str(e)}"

def rate_user_writing(client, user_text):
    """AI rates user's writing (1-5 scale)"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a writing critic. Rate the following text on a scale of 1-5 (5 being excellent) considering creativity, flow, grammar, and engagement. Respond with ONLY the number and a brief reason."},
                {"role": "user", "content": f"Rate this writing: {user_text}"}
            ],
            max_tokens=100,
            temperature=0.3
        )
        result = response.choices[0].message.content.strip()
        # Extract rating number
        rating = 3  # default
        if result and result[0].isdigit():
            rating = int(result[0])
        return rating, result
    except:
        return 3, "Unable to rate at this time"

def polish_writing(client, original_text, previous_ratings):
    """Polish user's writing and provide improvements"""
    try:
        # Adapt based on previous feedback
        rating_context = ""
        if previous_ratings:
            avg_rating = sum([r[0] for r in previous_ratings if r[0]]) / len([r for r in previous_ratings if r[0]])
            feedbacks = [r[1] for r in previous_ratings if r[1]]
            if avg_rating < 3:
                rating_context = "The user has been unsatisfied with previous edits. Be more conservative and focus on clear improvements. "
            if feedbacks:
                rating_context += f"Previous feedback: {'; '.join(feedbacks[-2:])}. "

        system_prompt = f"""You are an expert editor helping improve writing quality.
        {rating_context}
        
        Tasks:
        1. Improve grammar, flow, and clarity
        2. Enhance word choice and sentence structure
        3. Maintain the author's voice and style
        4. Fix any errors
        5. Make it more engaging while keeping the core meaning
        
        Preserve the original length and meaning."""
        
        with st.spinner("✨ Polishing your writing..."):
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Please polish and improve this text: {original_text}"}
                ],
                max_tokens=800,
                temperature=0.4
            )
            return response.choices[0].message.content.strip()
    
    except Exception as e:
        return f"❌ Error polishing text: {str(e)}"

# Initialize session state
def init_session_state():
    if 'current_story_id' not in st.session_state:
        st.session_state.current_story_id = None
    if 'current_polish_session' not in st.session_state:
        st.session_state.current_polish_session = None
    if 'story_mode' not in st.session_state:
        st.session_state.story_mode = 'new'
    if 'pending_ai_continuation' not in st.session_state:
        st.session_state.pending_ai_continuation = False
    if 'temp_user_chapter' not in st.session_state:
        st.session_state.temp_user_chapter = ""
    if 'temp_ai_style' not in st.session_state:
        st.session_state.temp_ai_style = "creative"
    if 'selected_ai_style' not in st.session_state:
        st.session_state.selected_ai_style = "creative"

# Main app
def main():
    st.set_page_config(page_title="AI Writing Assistant", page_icon="✍️", layout="wide")
    
    st.title("✍️ AI Writing Assistant")
    st.markdown("*Your personal AI writing companion for creative storytelling*")
    
    # Initialize database and session state
    init_db()
    init_session_state()
    
    # Check OpenAI connection
    client = get_openai_client()
    
    if not client:
        st.warning("🔑 Please configure your OpenAI API key to use AI features")
        return
    
    # Sidebar navigation - Updated order
    with st.sidebar:
        st.header("📚 Navigation")
        mode = st.radio("Choose mode:", ["✨ Text Polishing", "📖 Story Writing", "📊 Story List"])
    
    if mode == "✨ Text Polishing":
        text_polishing_mode(client)
    elif mode == "📖 Story Writing":
        story_writing_mode(client)
    else:
        story_list_mode()

def story_writing_mode(client):
    st.header("📖 Collaborative Story Writing")
    
    # Row 1: Choose to create new story or continue existing
    col1, col2 = st.columns(2)
    with col1:
        if st.button("➕ Create New Story", type="primary" if st.session_state.story_mode == 'new' else "secondary"):
            st.session_state.story_mode = 'new'
            st.session_state.current_story_id = None
            st.rerun()
    
    with col2:
        stories = get_stories()
        if stories:
            if st.button("📚 Continue Existing Story", type="primary" if st.session_state.story_mode == 'continue' else "secondary"):
                st.session_state.story_mode = 'continue'
                st.rerun()
    
    # Row 2: Story name input/display
    if st.session_state.story_mode == 'new':
        story_title = st.text_input("📝 Story Title:", placeholder="Enter your story title...")
        
        if story_title:
            # Two columns for writing interface
            col_left, col_right = st.columns(2)
            
            with col_left:
                st.markdown("### ✍️ Your Writing")
                user_text = st.text_area("Start your story (minimum 200 words):", height=400, 
                                       placeholder="Begin your story here...")
                
                word_count = len(user_text.split())
                st.markdown(f"**Word count:** {word_count}/200")
                
                # Let AI continue button (disabled if < 200 words)
                button_disabled = word_count < 200
                if st.button("🤖 Let AI continue the story", 
                           type="primary", 
                           disabled=button_disabled,
                           help="Write at least 200 words to enable AI continuation" if button_disabled else "Generate AI continuation"):
                    if 'selected_ai_style' in st.session_state:
                        # Create story
                        story_id = create_story(story_title, user_text)
                        st.session_state.current_story_id = story_id
                        st.session_state.story_mode = 'continue'
                        st.session_state.temp_user_chapter = user_text
                        st.session_state.temp_ai_style = st.session_state.selected_ai_style
                        st.session_state.pending_ai_continuation = True
                        st.rerun()
                
                # AI style selection - always visible
                st.markdown("### Tell AI what you want:")
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    if st.button("😂 Funny", 
                               type="primary" if st.session_state.get('selected_ai_style') == 'funny' else "secondary",
                               use_container_width=True):
                        st.session_state.selected_ai_style = 'funny'
                        st.rerun()
                
                with col2:
                    if st.button("👻 Spooky", 
                               type="primary" if st.session_state.get('selected_ai_style') == 'spooky' else "secondary",
                               use_container_width=True):
                        st.session_state.selected_ai_style = 'spooky'
                        st.rerun()
                
                with col3:
                    if st.button("🎲 Surprise", 
                               type="primary" if st.session_state.get('selected_ai_style') == 'surprise' else "secondary",
                               use_container_width=True):
                        st.session_state.selected_ai_style = 'surprise'
                        st.rerun()
                
                with col4:
                    if st.button("✨ Creative", 
                               type="primary" if st.session_state.get('selected_ai_style') == 'creative' else "secondary",
                               use_container_width=True):
                        st.session_state.selected_ai_style = 'creative'
                        st.rerun()
                
                # Initialize default style if not set
                if 'selected_ai_style' not in st.session_state:
                    st.session_state.selected_ai_style = 'creative'
            
            with col_right:
                st.markdown("### 🤖 AI Continuation")
                st.info("💡 Write at least 200 words and select a style to unlock AI continuation")
    
    elif st.session_state.story_mode == 'continue':
        if not st.session_state.current_story_id:
            # Select story to continue
            stories = get_stories()
            if stories:
                story_options = [f"{s[1]}" for s in stories]
                selected_title = st.selectbox("Select a story to continue:", story_options)
                
                if st.button("📖 Load Story"):
                    selected_idx = story_options.index(selected_title)
                    st.session_state.current_story_id = stories[selected_idx][0]
                    st.rerun()
            else:
                st.info("No stories found. Create a new story first!")
        else:
            # Display story and continue writing
            story_details = get_story_details(st.session_state.current_story_id)
            chapters = get_chapters(st.session_state.current_story_id)
            
            if story_details:
                st.markdown(f"## 📚 {story_details[0]}")
                
                # Handle pending AI continuation from new story creation
                if st.session_state.pending_ai_continuation:
                    # Rate user's writing
                    user_rating_score, user_rating_text = rate_user_writing(client, st.session_state.temp_user_chapter)
                    
                    # Generate AI continuation
                    ai_chapter = generate_next_chapter(client, st.session_state.temp_user_chapter, 
                                                     st.session_state.temp_user_chapter, 
                                                     st.session_state.temp_ai_style, [])
                    
                    # Save as first chapter
                    add_chapter(st.session_state.current_story_id, 1, 
                              st.session_state.temp_user_chapter, ai_chapter, 
                              st.session_state.temp_ai_style, user_rating_score)
                    
                    st.session_state.pending_ai_continuation = False
                    st.session_state.temp_user_chapter = ""
                    st.session_state.temp_ai_style = "creative"
                    st.rerun()
                
                # Display chapters in two columns
                col_left, col_right = st.columns(2)
                
                with col_left:
                    st.markdown("### ✍️ Your Writing")
                    
                    # Display original start
                    with st.expander("📝 Original Opening", expanded=False):
                        st.markdown(f"*{story_details[1]}*")
                    
                    # Display user chapters
                    for ch_num, user_content, _, _, _, ai_rating in chapters:
                        st.markdown(f"**Chapter {ch_num}**")
                        if ai_rating:
                            st.markdown(f"🤖 AI Rating: {'⭐' * ai_rating}")
                        st.markdown(f"{user_content}")
                        st.divider()
                    
                    # New chapter input
                    st.markdown("### ✍️ Write Next Chapter")
                    new_chapter = st.text_area("Continue your story (minimum 200 words):", 
                                             height=300, key="new_chapter_input")
                    
                    word_count = len(new_chapter.split())
                    st.markdown(f"**Word count:** {word_count}/200")
                    
                    # Let AI continue button (disabled if < 200 words)
                    button_disabled = word_count < 200
                    if st.button("🤖 Let AI continue the story", 
                               type="primary", 
                               disabled=button_disabled,
                               help="Write at least 200 words to enable AI continuation" if button_disabled else "Generate AI continuation",
                               key="continue_story_btn"):
                        if 'selected_ai_style' in st.session_state:
                            # Build story context
                            context = story_details[1] + "\n\n"
                            for ch_num, user_cont, ai_cont, _, _, _ in chapters:
                                context += f"Chapter {ch_num}: {user_cont}\n{ai_cont}\n\n"
                            
                            # Rate user's writing
                            user_rating_score, user_rating_text = rate_user_writing(client, new_chapter)
                            
                            # Get previous ratings
                            previous_ratings = get_user_rating_history(st.session_state.current_story_id)
                            
                            # Generate AI continuation
                            ai_chapter = generate_next_chapter(client, context, new_chapter, 
                                                             st.session_state.selected_ai_style, previous_ratings)
                            
                            # Save chapter
                            next_chapter_num = len(chapters) + 1
                            add_chapter(st.session_state.current_story_id, next_chapter_num, 
                                      new_chapter, ai_chapter, st.session_state.selected_ai_style, user_rating_score)
                            
                            st.success(f"✅ Chapter {next_chapter_num} created!")
                            st.info(f"💭 AI feedback on your writing: {user_rating_text}")
                            st.rerun()
                    
                    # AI style selection - always visible
                    st.markdown("### Tell AI what you want:")
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        if st.button("😂 Funny", 
                                   type="primary" if st.session_state.get('selected_ai_style') == 'funny' else "secondary",
                                   use_container_width=True,
                                   key="funny_btn"):
                            st.session_state.selected_ai_style = 'funny'
                            st.rerun()
                    
                    with col2:
                        if st.button("👻 Spooky", 
                                   type="primary" if st.session_state.get('selected_ai_style') == 'spooky' else "secondary",
                                   use_container_width=True,
                                   key="spooky_btn"):
                            st.session_state.selected_ai_style = 'spooky'
                            st.rerun()
                    
                    with col3:
                        if st.button("🎲 Surprise", 
                                   type="primary" if st.session_state.get('selected_ai_style') == 'surprise' else "secondary",
                                   use_container_width=True,
                                   key="surprise_btn"):
                            st.session_state.selected_ai_style = 'surprise'
                            st.rerun()
                    
                    with col4:
                        if st.button("✨ Creative", 
                                   type="primary" if st.session_state.get('selected_ai_style') == 'creative' else "secondary",
                                   use_container_width=True,
                                   key="creative_btn"):
                            st.session_state.selected_ai_style = 'creative'
                            st.rerun()
                    
                    # Initialize default style if not set
                    if 'selected_ai_style' not in st.session_state:
                        st.session_state.selected_ai_style = 'creative'
                
                with col_right:
                    st.markdown("### 🤖 AI Continuation")
                    
                    # Display AI chapters
                    for ch_num, _, ai_content, ai_style, user_rating, _ in chapters:
                        st.markdown(f"**Chapter {ch_num}** ({ai_style})")
                        
                        # Rating section
                        if user_rating:
                            st.markdown(f"👤 Your Rating: {'⭐' * user_rating}")
                        else:
                            col_a, col_b = st.columns([2, 1])
                            with col_a:
                                rating = st.selectbox(f"Rate this chapter:", 
                                                    [None, 1, 2, 3, 4, 5], 
                                                    key=f"rate_ch_{ch_num}")
                            with col_b:
                                if rating and st.button("Submit", key=f"submit_ch_{ch_num}"):
                                    update_chapter_rating(st.session_state.current_story_id, 
                                                        ch_num, rating)
                                    st.rerun()
                        
                        st.markdown(f"{ai_content}")
                        st.divider()
                    
                    if not chapters:
                        st.info("💡 AI continuation will appear here after you write your first chapter")

def text_polishing_mode(client):
    st.header("✨ Text Polishing Studio")
    st.markdown("*Get AI feedback and improvements on your writing*")
    
    # Text input
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 📝 Your Original Text")
        original_text = st.text_area("Write or paste your text here:", height=400,
                                   placeholder="Enter the text you'd like to improve...")
        
        if original_text:
            st.markdown(f"**Word count:** {len(original_text.split())}")
            
            if st.button("✨ Polish My Writing", type="primary"):
                # Get rating history for this polishing
                previous_ratings = get_user_rating_history(st.session_state.current_story_id or 0)
                
                # Rate original text
                ai_rating_score, ai_rating_text = rate_user_writing(client, original_text)
                
                # Polish the text
                polished_text = polish_writing(client, original_text, previous_ratings)
                
                # Save polish session
                session_id = add_polish_session(st.session_state.current_story_id or 0, 
                                              original_text, polished_text, ai_rating_score)
                st.session_state.current_polish_session = session_id
                
                st.rerun()
    
    with col2:
        st.markdown("### ✨ AI Enhanced Version")
        
        if st.session_state.current_polish_session:
            # Display polished text
            conn = sqlite3.connect('writing_sessions.db')
            c = conn.cursor()
            c.execute("SELECT original_text, polished_text, ai_rating FROM polish_sessions WHERE id = ?", 
                     (st.session_state.current_polish_session,))
            result = c.fetchone()
            conn.close()
            
            if result:
                polished_text = result[1]
                ai_rating = result[2]
                
                st.markdown(f"🤖 **AI's rating of your original:** {'⭐' * ai_rating}/5")
                st.divider()
                st.markdown(polished_text)
                st.markdown(f"**Word count:** {len(polished_text.split())}")
                
                # Rating system
                st.divider()
                st.markdown("### 📊 Rate the AI's Polish")
                
                col_a, col_b = st.columns(2)
                with col_a:
                    user_rating = st.selectbox("Your rating:", [None, 1, 2, 3, 4, 5])
                with col_b:
                    if user_rating:
                        feedback = st.text_input("Optional feedback:", 
                                               placeholder="What could be better?")
                        if st.button("Submit Rating"):
                            update_polish_rating(st.session_state.current_polish_session, 
                                               user_rating, feedback)
                            st.success("Thanks for your feedback! AI will improve.")
                            st.session_state.current_polish_session = None
                            st.rerun()
        else:
            st.info("👈 Enter text on the left to see AI improvements here")

def story_list_mode():
    st.header("📊 Story List")
    
    stories = get_stories()
    
    if not stories:
        st.info("📚 No stories yet! Create your first story in Story Writing mode.")
        return
    
    # Create a table-like display
    for i, (story_id, title, created_at) in enumerate(stories, 1):
        with st.expander(f"{i}. 📚 {title}"):
            chapters = get_chapters(story_id)
            
            # Display metrics
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("📅 Created", created_at[:10])
            
            with col2:
                st.metric("📖 Chapters", len(chapters))
            
            with col3:
                if chapters:
                    ai_ratings = [ch[5] for ch in chapters if ch[5]]
                    if ai_ratings:
                        avg_ai_rating = sum(ai_ratings) / len(ai_ratings)
                        st.metric("🤖 Avg AI Rating", f"{avg_ai_rating:.1f}/5")
                    else:
                        st.metric("🤖 Avg AI Rating", "N/A")
            
            with col4:
                user_ratings = [ch[4] for ch in chapters if ch[4]]
                if user_ratings:
                    avg_user_rating = sum(user_ratings) / len(user_ratings)
                    st.metric("👤 Your Avg Rating", f"{avg_user_rating:.1f}/5")
                else:
                    st.metric("👤 Your Avg Rating", "N/A")
            
            # Show chapter summary
            if chapters:
                st.markdown("**Chapter Summary:**")
                for ch_num, _, _, ai_style, user_rating, ai_rating in chapters[-3:]:  # Show last 3 chapters
                    st.markdown(f"• Chapter {ch_num} ({ai_style}) - "
                              f"AI: {'⭐' * (ai_rating or 0)}, "
                              f"You: {'⭐' * (user_rating or 0) if user_rating else 'Not rated'}")
            
            # Continue button
            if st.button(f"📖 Continue This Story", key=f"continue_{story_id}"):
                st.session_state.current_story_id = story_id
                st.session_state.story_mode = 'continue'
                st.success("Story loaded! Switch to 📖 Story Writing mode to continue.")
                st.rerun()

if __name__ == "__main__":
    main()
