import streamlit as st
from PyPDF2 import PdfFileReader
import streamlit_authenticator as stauth
# import json
from PIL import Image
import os
from dotenv import load_dotenv
from utils import AWSTexttract, LangChainAI, AWSS3, AWSTranscribe, DynamoDBManager
import yaml
from yaml.loader import SafeLoader
# from trubrics.integrations.streamlit import FeedbackCollector
import logging
load_dotenv('.env', override=True)
from mutagen.mp3 import MP3
from st_files_connection import FilesConnection
import datetime
from decimal import Decimal
from streamlit_cognito_auth import CognitoAuthenticator #https://github.com/pop-srw/streamlit-cognito-auth
# import subprocess

lang="ITA"
JOB_URI="s3://riassume-transcribe-bucket/"
S3_BUCKET='riassume-transcribe-bucket'
COGNITO_USER_POOL='us-east-1_2gJgqtGK3'
COGNITO_CLIENT_ID='1hbdf29bl3goifqovdsga02kov'
table_name = "chatgpt-summary-users"
langchain_client = LangChainAI()
s3_client=AWSS3('riassume-document-bucket')
conn = st.experimental_connection('s3', type=FilesConnection)
transcribe_s3client = AWSS3(S3_BUCKET)
transcribe = AWSTranscribe(JOB_URI)
textract = AWSTexttract()
dynamo_manager = DynamoDBManager(os.getenv('AWS_REGION'), table_name)
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
UPLOAD_FOLDER = '/tmp' #on Linux/Docker
# UPLOAD_FOLDER = r"C:\Users\ELAFACRB1\Codice\GitHub\chatgpt-summmary\uploads" #on Winzozz
SQS_URL = os.getenv('SQS_URL')

# Configurazione della pagina Streamlit
# st.set_page_config(page_title="Riassume: l'AI a supporto degli studenti", page_icon=":memo:", layout="wide")

def speech_to_text(job_name, lang_code):
    job_name=transcribe.generate_job_name()
    data = transcribe.amazon_transcribe(JOB_URI, job_name, uploaded_mp3.name, lang_code)
    logger.info("File audio transcribed!")
    return data

### Cognito login #FIXME
# authenticator = CognitoAuthenticator(
#     pool_id=COGNITO_USER_POOL,
#     app_client_id=COGNITO_CLIENT_ID,
# )
# is_logged_in = authenticator.login()
# username = authenticator.get_username()

# # Inizio pagina
# if is_logged_in == True:
if True:

    username = 'test'

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["AUDIO", "TESTO", "WEB", "VIDEO", "CHAT", "I MIEI RIASSUNTI"])

    try: 
        USER_ID = dynamo_manager.get_item({"username": username})['Item']['username']
    except Exception as e:
        st.error("Login fallito. Riprova.")
        raise Exception("User not found!")
    
    with tab1:
        st.title("Benvenuto, " + username + "!")

        ########### Riasusmi da una registrazione ###########
        st.title("Sbobina una registrazione")
        st.write("Per favore converti il file in mp3. Presto saranno supportati nuovi formati audio.")
        uploaded_mp3 = st.file_uploader("Carica un file MP3", type=["mp3"])
        
        if uploaded_mp3 is not None:
            if st.button('Elabora il file audio'):
                    
                with open(os.path.join(UPLOAD_FOLDER, uploaded_mp3.name), 'wb') as f:
                    f.write(uploaded_mp3.read())
                # Convert m4a to mp3 #FIXME: doesn't work
                # if uploaded_mp3.name.endswith('.m4a'):
                #     CurrentFileName= os.path.join(UPLOAD_FOLDER, uploaded_mp3.name)
                #     FinalFileName = os.path.join(UPLOAD_FOLDER, uploaded_mp3.name[:-4] + '.mp3')
                #     try:
                #         subprocess.call(['ffmpeg', '-i', f'{CurrentFileName}', f'{FinalFileName}'])
                #     except Exception as e:
                #         print(e)
                #         print('Error While Converting Audio')
                #     uploaded_mp3.name = FinalFileName
                with st.spinner('Elaborazione, per favore attendi...'):
                    transcribe_s3client.upload_file(os.path.join(UPLOAD_FOLDER, uploaded_mp3.name),uploaded_mp3.name)
                    audio = MP3(os.path.join(UPLOAD_FOLDER, uploaded_mp3.name))
                    duration = audio.info.length
                    os.remove(os.path.join(UPLOAD_FOLDER, uploaded_mp3.name))

                    #Check user timeouts
                    get_key = {"username": username}
                    if dynamo_manager.get_item(get_key)['Item']['time_limit'] < 0:
                        st.error("Non hai più minuti disponibili per la versione di prova! Contattaci per continuare ad usare l'applicazione.")
                        raise Exception("User out of time!")
                    else:
                        ## Speech-to-text
                        logger.info("Transcribing audio file...")

                        ## Speech-to-text module
                        data = speech_to_text(uploaded_mp3.name, 'it-IT')

                        ## Summarize module
                        try:
                            # Riassunto dei testi
                            summarized_data = langchain_client.summarize_text(data)
                        
                            # Creazione lista argomenti
                            bullet_point_text = langchain_client.bullet_point_text(summarized_data)
                            logger.info("Audio file summarized!")

                        except Exception as e:
                            logger.error(e)
                            st.error("Il file audio è troppo lungo, stiamo lavorandop er aumentare il limite, nel frattempo prova a dividere il file audio in più parti, ci scusiamo per l'inconveniente.")
                            # raise Exception("Summarize timeout!")

                        try:
                            ## Create file testo
                            with open(os.path.join(UPLOAD_FOLDER, 'tmp.txt'), 'w', encoding='utf-8') as f:
                                f.write("Contenuo audio: \n\n")
                                f.write(summarized_data)
                                f.write('Argomenti principali trattati: \n\n')
                                f.write(bullet_point_text)
                                

                            ## Upload file testo
                            s3_client.upload_file(os.path.join(UPLOAD_FOLDER, 'tmp.txt'), username+'/'+"Argomenti audio "+str(uploaded_mp3.name)+".txt")
                            #Remove tmp file
                            os.remove(os.path.join(UPLOAD_FOLDER, 'tmp.txt')) 
                            st.success("Nota carica con successo!")

                            ## Update user timeouts
                            update_expression = "SET time_limit = :new_value"
                            expression_values = {":new_value": dynamo_manager.get_item(get_key)['Item']['time_limit']-Decimal(duration)}
                            dynamo_manager.update_item(get_key, update_expression, expression_values)
                        
                        except Exception as e:
                            logger.error(e)
                            st.error("Errore durante il caricamento della nota. Riprova o contatta l'assistenza.")

    
    with tab2:

        ########### Riasusmi da un libro ###########
        st.title("Riassumi da PDF")
        # Definizione dell'area di drag and drop
        uploaded_files = st.file_uploader("Carica i file qui", type=["jpg", "png", "pdf"], accept_multiple_files=True)

        #Elabora i file caricati tramite openai
        if st.button("Elabora i file testuali"):
            if uploaded_files is not None:
                with st.spinner('Elaborazione, per favore attendi...'):
                    text_input = []
                    for file in uploaded_files:
                        filename= file.name
                        if file.type == "application/pdf":
                            pdf_reader = PdfFileReader(file)
                            for page in pdf_reader.pages:
                                text = page.extractText()
                                text_input.append(text.replace('\n', ' '))
                        elif file.type == "image/jpeg" or file.type == "image/png" or file.type == "image/jpg":             
                            img1 = Image.open(file)
                            rgb_im = img1.convert('RGB') #to convert png to jpg
                            text = textract.get_text(rgb_im).replace('\n', ' ')
                            text_input.append(text.replace('\n', ' '))
                        
                        else:
                            st.write("Formato non supportato.")
                    
                    #Salva response
                    response = langchain_client.final_chain(text_input)
                    with open(os.path.join(UPLOAD_FOLDER, 'tmp.txt'), 'w', encoding='utf-8') as f:
                        f.write(response)
                    ## Upload file testo
                    s3_client.upload_file(os.path.join(UPLOAD_FOLDER, 'tmp.txt'), username+'/'+"Argomenti foto "+str(filename)+".txt")
                    #Remove tmp file
                    os.remove(os.path.join(UPLOAD_FOLDER, 'tmp.txt'))
                    st.success("Nota carica con successo!")

                    ## Update user counter
                    get_key = {
                            "username": username
                        }
                    update_expression = "SET n_images = :new_counter"
                    expression_values = {
                        ":new_counter": dynamo_manager.get_item(get_key)['Item']['n_images']+1
                    }
                    dynamo_manager.update_item(get_key, update_expression, expression_values)

            else:
                st.write("Nessun file caricato.")


        ########### Elaborazione testi ###########
        st.title("Scrivi una nota")
        st.write("Usa la sezione sottostante e seleziona un'opzione dal menù a tendina per elaborare il testo.")

        text_name = st.text_input("Inserisci il titolo")

        # Definizione dell'area di testo
        text_input = st.text_area("Inserisci i tuoi appunti qui")

        # Definizione del menù a tendina
        choice = st.selectbox("Scegli un'opzione", ["riassumere", "parafrasare", "arricchire", "minuta"])

        # Definizione del pulsante di invio
        if st.button("Salva", disabled=False):
            with st.spinner('Elaborazione, per favore attendi...'):
                if choice == "riassumere":
                    res = langchain_client.summarize_text(text_input)
                    st.write(res)
                elif choice == "parafrasare":
                    res = langchain_client.paraphrase_text(text_input)
                    st.write(res)
                elif choice == "arricchire":
                    res = langchain_client.expand_text(text_input)
                    st.write(res)
                elif choice == "minuta":
                    res = langchain_client.draft_text(text_input)
                    st.write(res)
            
                #Salva response
                with open(os.path.join(UPLOAD_FOLDER, 'tmp.txt'), 'w', encoding='utf-8') as f:
                    f.write(text_name)
                    f.write('\n\n')
                    f.write(res)
                ## Upload file testo
                s3_client.upload_file(os.path.join(UPLOAD_FOLDER, 'tmp.txt'), username+'/'+"Nuova nota - "+ (choice) + " - " + str(datetime.datetime.now())+".txt")
                #Remove tmp file
                os.remove(os.path.join(UPLOAD_FOLDER, 'tmp.txt'))
                st.success("Nota carica con successo!")

    with tab3:
        st.write("COMING SOON")

    
    with tab4:
        st.write("COMING SOON")

    with tab5:
        st.write("COMING SOON")


    with tab6:
        list_contents=s3_client.list_items(username)
        for content in list_contents:
            st.header(s3_client.read_metadata(content['Key'], 'name').replace(username+"/", ''))
            text = conn.read("riassume-document-bucket/"+content['Key'], input_format="text", ttl=600)
            st.write(text)
            st.write("")
        
# else:
#     st.error("Login fallito. Riprova.")