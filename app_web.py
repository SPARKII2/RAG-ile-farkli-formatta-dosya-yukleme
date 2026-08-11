import streamlit as st
import tempfile
import os
import fitz 
import pytesseract
from PIL import Image
import chromadb
from chromadb.utils.embedding_functions import OllamaEmbeddingFunction
import ollama
import io
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
import sqlite3
import re
import easyocr as es
from pdf2image import convert_from_path as cfp

st.set_page_config(page_title='RAG' , page_icon='✨')
if 'mode' not in st.session_state:
    st.session_state.mode = 'home'


if "chroma_path" not in st.session_state:
    st.session_state.chroma_path = tempfile.mkdtemp()

def model(prompt):
    yanit = ollama.chat(model='granite4.1:8b' , messages=[{'role':'user','content':prompt}],options={"temperature": 0.0,"num_gpu":99})
    return yanit

def cevap(soru , koliskiyon):
    arama_sonucu=koliskiyon.query(query_texts=[soru] , n_results=15)
    baglam = "\n".join(arama_sonucu['documents'][0])
    prompt = f"""
    Sana verilen aşağıdaki belge içeriğine dayanarak kullanıcının sorusuna yanıt ver.
    
    Talimatlar:
    1. Eğer kullanıcı belgenin özetini, konusunu veya genel bakışını istiyorsa; verilen tüm bağlamı analiz ederek ana noktaları maddeler halinde özetle.
    2. Sorulan spesifik soruya belgede yanıt varsa net ve kendi cümlelerinle açıklayarak cevapla.
    3. Eğer sorunun yanıtı veya konusu verilen bağlamda kesinlikle yoksa sadece "Belgede bu bilgi bulunmuyor." de.
    
    Belge İçeriği:
    {baglam}
    
    Kullanıcının Sorusu: {soru}
    """
    yanit = model(prompt)
    return yanit['message']['content']
    

def sema_al(db_yolu):
    baglanti = sqlite3.connect(db_yolu)

    cursor = baglanti.cursor()
    cursor.execute("select name from sqlite_master where type='table';")
    tablolar = cursor.fetchall()
    sema_metni=""
    for tablo in tablolar:
        tablo_adi = tablo[0]
        if tablo_adi.startswith('sqlite_'):
            continue
        cursor.execute(f"PRAGMA table_info([{tablo_adi}]);")
        sutunlar = cursor.fetchall()
        sutun_isimleri = [sutun[1] for sutun in sutunlar]
        sema_metni += f"-Tablo: {tablo_adi} (Sütunlar: {','.join(sutun_isimleri)})\n"
    baglanti.close()
    return(sema_metni)


def sql_uret(soru, sema_metni):
    prompt = f"""You are an expert SQLite SQL developer.
Schema:
{sema_metni}

CRITICAL RULES:
1. Output ONLY 1 valid SQLite SELECT query. DO NOT write explanations, comments, markdown code blocks (like ```sql), or any extra text. Start directly with 'SELECT'.
2. If table or column names contain spaces, enclose them in brackets: [Order Details].
3. If The schema and database are in English. Match search terms accordingly (e.g., 'Spain', 'Germany'). 
4. ALWAYS properly close all single quotes (') and parentheses. Double-check your string literals.
5. When asked for records with no matching child records (e.g., customers with no orders), NEVER use 'NOT IN'. Instead, use 'LEFT JOIN ... WHERE ... IS NULL' or 'NOT EXISTS'.
6. For quantities, total sales, or best-selling products, prefer 'INNER JOIN' over subqueries and aggregate using 'SUM(CAST(od.Quantity AS INTEGER))'.
7. When CategoryName is requested, join the Categories table. When customer Country is requested, join the Customers table.

Question: {soru}
SQL:"""

    response = model(prompt)

    sql_sorgusu = response["message"]["content"].strip()
    sql_sorgusu = re.sub(r"```(?:sql)?","",sql_sorgusu,flags=re.IGNORECASE).strip("`'\" \n\r\t")

    if sql_sorgusu.lower().startswith("sql"):
        sql_sorgusu = sql_sorgusu[3:].strip()
    if";" in sql_sorgusu:
        sql_sorgusu=sql_sorgusu.split(";")[0]+";"

    return sql_sorgusu


def sql_clistir(db_yolu , sql_sorgusu):
    try:
        baglanti = sqlite3.connect(db_yolu)
        cursor = baglanti.cursor()
        cursor.execute(sql_sorgusu)
        sonuclar = cursor.fetchall()
        sutun_headers = [description[0] for description in cursor.description]
        baglanti.close()
        return sonuclar,sutun_headers,None
    except Exception as e:
        return None,None,str(e)


def clinet_olustur():
    chroma_client = chromadb.PersistentClient(path = st.session_state.chroma_path)
    return chroma_client
ollama_ef = OllamaEmbeddingFunction(url="http://localhost:11434",
    model_name='nomic-embed-text')

ollama_ef._client.timeout = 300.0

def metin_parcala(metin):
    sayac = 0
    liste =[]
    gecici_metin = ''
    for karekter in metin:
        gecici_metin += karekter
        sayac+=1
        if sayac >= 500 and karekter in [',' ,'.','?','!']:
            liste.append(gecici_metin)
            gecici_metin = ''
            sayac = 0
    liste.append(gecici_metin)
    return liste




def dosayi_ac(gecici_dosya):
    metin = ''
    uzanti = os.path.splitext(gecici_dosya)[1].lower()
    if uzanti in ['.png','.jpg','.jpeg']:
        resim = Image.open(gecici_dosya)
        metin= pytesseract.image_to_string(resim , lang='tur+ara+eng',config='--psm 11')
    elif uzanti == ".pdf":
        doc = fitz.open(stream=yuklenen_dosya.read() , filetype='pdf')
        for sayfa in doc:
            pix = sayfa.get_pixmap()
            resim = Image.open(io.BytesIO(pix.tobytes('png')))
            metin+=pytesseract.image_to_string(resim,lang='tur+ara+eng',config='--psm 11')
    elif uzanti in ['.sql' , '.txt' , '.py','.md']:
        gecici_dosya.seek(0)
        metin = gecici_dosya.read().decode('utf-8-sig' , errors='ignore')

    else:
        st.error('desteklenmeyen bir dosya yuklediniz')
    return metin
with st.sidebar:
        yuklenen_dosya = st.file_uploader('bir dosya yukleyin' , type=['pdf' , 'png' ,'jpg','.jpeg','sql' , 'txt','py' , 'md','db' , 'sqlite','sqlite3'])
        if yuklenen_dosya is not None:
            uzanti = os.path.splitext(yuklenen_dosya.name)[1]
            with tempfile.NamedTemporaryFile(delete=False  , suffix=uzanti) as temp:
                temp.write(yuklenen_dosya.getvalue())
                st.session_state.dosya = temp.name
            #st.session_state.dosya = yuklenen_dosya.name
            if st.button(label='Dosyalari isle'):
                if uzanti in ['.db' , '.sqlite' , '.sqlite3']:
                    st.session_state.mode = 'sql'
                else:
                    st.session_state.mode = 'yukle'
            if st.session_state.mode  == 'yukle':
                metin = dosayi_ac(st.session_state.dosya)
                chroma_client =clinet_olustur()
                parcalar = metin_parcala(metin)
                koleksiyon = chroma_client.get_or_create_collection(name = "dokumanlar",embedding_function=ollama_ef)
                batch_size = 200
                for i in range(0,len(parcalar) , batch_size):
                    batch_parcalar = parcalar[i:i+batch_size]
                    batch_ids = [f"id_{j}" for j in range(i,i+len(batch_parcalar))]
                    koleksiyon.add(documents=batch_parcalar,ids=batch_ids)
                    toplam_parca = len(parcalar)
                st.success('belge basariyla islendi')
                st.session_state.mode = 'chat'
            elif st.session_state.mode =='sql':
                #with tempfile.NamedTemporaryFile(delete=False , suffix=uzanti) as gecici_dosya:
                #    gecici_dosya.write(yuklenen_dosya.getvalue())
                #chroma_client = clinet_olustur()
                #koleksiyon = chroma_client.get_or_create_collection(name = "dokumanlar",embedding_function=ollama_ef)
                st.success('sql belge basariyla islendi')
                st.session_state.mode = 'sql_chat'

if st.session_state.mode == 'sql_kontrol':
    try:
        if st.session_state.userName is not ''  and st.session_state.password is not '':
            st.session_state.mode = 'sql_chat'
        else:
            st.session_state.mode = "yanlis"

    except:
        st.write('dustu')
        st.session_state.mode = 'giris_yapilmadi'






if st.session_state.mode == 'chat':
    soru = st.chat_input('bir soru sorun')

    chroma_client = clinet_olustur()
    if 'messages' not in st.session_state:
        st.session_state.messages=[]
        
    for i in st.session_state.messages:
        with st.chat_message(i['role']):
            st.write(i['content'])
    if soru:
        st.chat_message('user').write(soru)
        st.session_state.messages.append({'role':'user' ,'content':soru})

        koleksiyon = chroma_client.get_or_create_collection(name='dokumanlar',embedding_function=ollama_ef)

        
        with st.spinner("cevap hazirlaniyor..."):
            gelen_cevap = cevap(soru,koleksiyon)
            st.chat_message('assistant').write(gelen_cevap)
            st.session_state.messages.append({'role':'assistant' , 'content':gelen_cevap})
elif st.session_state.mode == 'sql_chat':
    soru = st.chat_input("bir soru sorun")
    if 'messages' not in st.session_state:
        st.session_state.messages=[]
        
    for i in st.session_state.messages:
        with st.chat_message(i['role']):
            st.write(i['content'])
    if soru:
        st.chat_message('user').write(soru)
        st.session_state.messages.append({'role':'user' ,'content':soru})
        sema = sema_al(st.session_state.dosya)
        sql = sql_uret(soru,sema)
        sonuclar , sutunlar , hata = sql_clistir(st.session_state.dosya,sql)
        if hata:
            st.error(f"sql hatasi: {hata}")
        prompt_ozet = f"""Sana veritabanından alınan CANLI VE GERÇEK veriler verildi.
        GÖREVİN: Sadece ve sadece sana verilen bu verileri kullanarak Türkçe cevap üretmek.

        Kullanıcı Sorusu: "{soru}"
        Sütunlar: {sutunlar}
        Veritabanından Dönen Gerçek Veri: {sonuclar}

        KURAL:
        1. Eğer veride ne yazıyorsa BİREBİR onu söyle. Kafandan başka ürün adı veya sayı UYDURMA!
        2. Veri boşsa "Veritabanında kayıt bulunamadı" de.

        Cevap:"""
        with st.spinner('cevap hazirlaniyor'):
            cevap2 = model(prompt_ozet)

        mes = cevap2['message']['content']
        st.chat_message('assistant').write(mes)
        st.session_state.messages.append({'role':'assistant' , 'content':mes})

elif st.session_state.mode == "giris_yapilmadi" or st.session_state.mode == 'yanlis':
    if st.session_state.mode == 'yanlis':
        st.error("Girdiniz Bilgiler Yanlis")
    else:
        st.write("giris yapin")

    with st.form('login_form'):
        st.session_state.userName = st.text_input("Kullanici Adi Giriniz")
        st.session_state.password = st.text_input("Sifreyi Giriniz")
        st.form_submit_button('Giris Yap')
    st.session_state.mode = 'sql_kontrol'

else:
    st.error('once bir belge yukleyin')


 
#sqlite Rag yontemi
#     elif uzanti in ['.sqlite3' , '.sqlite', '.db']:
#         with tempfile.NamedTemporaryFile(delete=False , suffix='.db') as gecici:
#             gecici.write(gecici_dosya.getvalue())
#         gecici_veritaban = gecici.name
#         baglanti =sqlite3.connect(gecici_veritaban)
#         baglanti.row_factory = sqlite3.Row
#         cursor = baglanti.cursor()
#         baglanti.text_factory=lambda x:str(x , 'utf-8' , errors='ignore')
#         cursor.execute("select name from sqlite_master where type ='table'; ")
#         tablolar = cursor.fetchall()

#         tum_parcalar = []
#         tum_metadatalar=[]
#         tum_idler =[]
#         for tablo in tablolar:
#             tablo_adi = tablo[0]
#             if tablo_adi.startswith('sqlite_'):
#                 continue
#             cursor.execute(f"select * from [{tablo_adi}]")
#             satirlar = cursor.fetchall()
#             for idx,satir in enumerate(satirlar):
#                 sutun_bilgileri = ", ".join([f"{sutun}: {satir[sutun]}" for sutun in satir.keys()])
#                 parca_metin = f"Tablo: {tablo_adi} | {sutun_bilgileri}"
#                 tum_parcalar.append(parca_metin)
#                 tum_metadatalar.append({"tablo": tablo_adi})
#                 tum_idler.append(f"{tablo_adi}_{idx}")
#         baglanti.close()  
#         chroma_client =clinet_olustur() 
#         try:
#             chroma_client.delete_collection(name='dokumanlar')
#         except:
#             pass
#         koleksiyon = chroma_client.get_or_create_collection(name = "dokumanlar",embedding_function=ollama_ef)    
#         batch_size = 200
#         for i in range(0,len(tum_parcalar) , batch_size):
#             batch_parcalar = tum_parcalar[i:i+batch_size]
#             koleksiyon.add(documents=batch_parcalar,
#                            metadatas=tum_metadatalar[i:i+batch_size],
#                            ids=tum_idler[i:i+batch_size])
#             print(f"{i+len(batch_parcalar)}/{len(tum_parcalar)} tamamlandi")
