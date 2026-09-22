import google.generativeai as genai
import cv2
import numpy as np
from PIL import Image
import os

from dotenv import load_dotenv
load_dotenv() #activate api key

def extract_text_image(image_path):
    file_bytes = np.asarray(bytearray(image_path.read()), dtype=np.uint8)
    image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    # lets Load and Process the image
    #image = cv2.imread(image) # Load the image
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB) # To convert BGR to RGB
    image_grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) # To convert BGR to Grey
    _,image_bw = cv2.threshold(image_grey,150,255,cv2.THRESH_BINARY) # B&W conversion

    # The image that CV2 gives is in numpy array format, we need to convert it to image object
    final_image = Image.fromarray(image_bw) 

    # Configure genai Model
    key = os.getenv("GOOGLE_API_KEY")
    genai.configure(api_key=key)
    model = genai.GenerativeModel('gemini-2.5-flash-lite')

    # Lets write prompt for OCR
    prompt = '''You act as an OCR application on the given image and extract the text from it.
            Give only the text as output, do not give any other explanation or description.'''
    
    # Lets extrcat and return the text
    response = model.generate_content([prompt,final_image])
    output_text = response.text
    return output_text