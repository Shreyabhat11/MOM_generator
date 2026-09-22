import google.genai as genai
import os
import streamlit as st
from pdfextractor import text_extractor_pdf
from docxextractor import text_extractor_docx
from imageextractor import extract_text_image

from dotenv import load_dotenv
load_dotenv() #activate api key

# Configure The Model
key = os.getenv('GOOGLE_API_KEY')
genai.configure(api_key=key)
model = genai.GenerativeModel('gemini-2.5-flash-lite')


# Upload file in Sidebar
user_text = None
st.sidebar.title(':orange[Upload yor MoM notes here: ]')
st.sidebar.subheader("Only Upload Images, PDF's and DOCX")
user_file = st.sidebar.file_uploader("Upload your file", type=['pdf', 'docx', 'png', 'jpg', 'jpeg'])
if user_file:
    if user_file.type == 'application/pdf':
        user_text = text_extractor_pdf(user_file)
    elif user_file.type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
        user_text = text_extractor_docx(user_file)
    elif user_file.type in ['image/jpg','image/jpeg','image/png']:
        user_text = extract_text_image(user_file)
    else:
        st.sidebar.error('Upload Correct File Format')

# Main page
st.title(':blue[Minutes Of Meeting] : :green[AI assisted MoM generator in a standardized form from meeting notes.]')
tips = '''Tips to use this app:
* Upload your meeting in side bar (Image, PDF or DOCX)
* Click on generate MoM and get the standardized MoM's'''
st.write(tips)
    
if st.button('Generate MoM'):
    if user_text is None:
        st.error('Text is not generated')

    else:
        with st.spinner('Processing you data....'):
            prompt = f'''Assume you are expert in creating minutes of meeting. User has provided
            notes of meeting in text format. Using this data you need to create a standardized
            minutes of meeting for the user. 

            Output must follow word/docx format, strictly in the following manner:
            title : Title of meeting
            Heading : Meeting Agenda
            subheading : Name of attendees (If attendees name is not there keep it NA)
            subheading : date of meeting and place of meeting (place means name of conference /meeting room if not provided keep it online)
            Body: The body must follow the following sequence of points
            * Key points discussed
            * Highlight any decision that has been finalised.
            * mention actionable items.
            * Any additional notes.
            * Any deadline that has been discussed.
            * Any next meeting date that has been discussed.
            * 2 to 3 line of summary.
            * Use bullet points and highlight or bold important keywords such the context is clear.
            * Generate the output in such a format that it can can be copied and paste in word and create pdf.
            
            The data provided by user is as follows {user_text}'''

            response = model.generate_content(prompt)
            st.write(response.text)

            st.download_button(label='Click To Download',
                               data=response.text,
                               file_name='MoM.txt',
                               mime='text/plain')
