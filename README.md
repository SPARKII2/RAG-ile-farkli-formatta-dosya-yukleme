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

bu kutuphaneleri kulllanarak ve granite4.1:8b modeli kullanarak tasarlanan system.
farkli formatta dosya yukleyip o dosya ile ilgili soru sorabilirsiniz 
