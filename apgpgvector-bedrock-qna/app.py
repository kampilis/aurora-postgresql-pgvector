import streamlit as st
from dotenv import load_dotenv
from PyPDF2 import PdfReader
from langchain.vectorstores.pgvector import PGVector
from langchain.memory import ConversationSummaryBufferMemory
from langchain.chains import ConversationalRetrievalChain
from htmlTemplates import css
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.embeddings import BedrockEmbeddings
from langchain.llms import Bedrock
from langchain.prompts import PromptTemplate
import boto3
from PIL import Image
import os
import traceback

def get_pdf_text(pdf_docs):
    text = ""
    for pdf in pdf_docs:
        pdf_reader = PdfReader(pdf)
        for page in pdf_reader.pages:
            text += page.extract_text()
    return text

def get_text_chunks(text):
    text_splitter = RecursiveCharacterTextSplitter(
        separators=["\n\n", "\n", ".", " "],
        chunk_size=1000, 
        chunk_overlap=200, 
        length_function=len
     )

    chunks = text_splitter.split_text(text)
    return chunks


def get_vectorstore(text_chunks):
    embeddings = BedrockEmbeddings(model_id= "amazon.titan-embed-g1-text-02", client=BEDROCK_CLIENT)
    if text_chunks is None:
        return PGVector(
            connection_string=CONNECTION_STRING,
            embedding_function=embeddings,
        )
    return PGVector.from_texts(texts=text_chunks, embedding=embeddings, connection_string=CONNECTION_STRING)
        

def get_conversation_chain(vectorstore):
    # Use Claude
    llm = Bedrock(model_id="anthropic.claude-v2", client=BEDROCK_CLIENT)
    llm.model_kwargs = {"temperature": 0.5, "max_tokens_to_sample": 8191}
    
    prompt_template = """
    Human: You are a helpful assistant that answers questions in detail and only using the information provided in the context below. 
    Guidance for answers:
        - Always use English as the language in your responses.
        - In your answers, always use a professional tone.
        - Begin your answers with "Based on the context provided: "
        - Simply answer the question clearly and with lots of detail using only the relevant details from the information below. If the context does not contain the answer, say "Sorry, I didn't understand that. Could you rephrase your question?"
        - Use bullet-points and provide as much detail as possible in your answer. 
        - Always provide a summary at the end of your answer.
        
    Now read this context below and answer the question at the bottom.
    
    Context: {context}

    Question: {question}
    
    Assistant:"""

    PROMPT = PromptTemplate(
        template=prompt_template, input_variables=["context", "question"]
    )
    
    memory = ConversationSummaryBufferMemory(
        llm=llm,
        memory_key='chat_history',
        return_messages=True,
        ai_prefix="Assistant",
        output_key='answer')
    
    conversation_chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        chain_type="stuff",
        return_source_documents=True,
        retriever=vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={"k": 3, "include_metadata": True}),
        get_chat_history=lambda h : h,
        memory=memory,
        combine_docs_chain_kwargs={'prompt': PROMPT}
    )
    
    return conversation_chain


def handle_userinput(user_question):
    
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = None
    
    if "messages" not in st.session_state:
        st.session_state.messages = []
        
    try:
        response = st.session_state.conversation({'question': user_question})
        
    except ValueError:
        st.write("Sorry, I didn't understand that. Could you rephrase your question?")
        print(traceback.format_exc())
        return

    st.session_state.chat_history = response['chat_history']

    for i, message in enumerate(st.session_state.chat_history):
        if i % 2 == 0:
            st.success(message.content, icon="🤔")
        else:
            st.write(message.content)

def main():
    st.set_page_config(page_title="Generative AI Q&A with Amazon Bedrock, Aurora PostgreSQL and pgvector",
                       layout="wide",
                       page_icon=":books::parrot:")
    st.write(css, unsafe_allow_html=True)

    logo_url = "static/Powered-By_logo-stack_RGB_REV.png"
    st.sidebar.image(logo_url, width=150)

    st.sidebar.markdown(
    """
    ### Instructions:
    1. Browse and upload PDF files
    2. Click Process
    3. Type your question in the search bar to get more insights
    """
    )

    if "conversation" not in st.session_state:
        st.session_state.conversation = get_conversation_chain(get_vectorstore(None))
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = None

    st.header("Generative AI Q&A with Amazon Bedrock, Aurora PostgreSQL and pgvector :books::parrot:")
    subheader = '<p style="font-family:Calibri (Body); color:Grey; font-size: 16px;">Leverage Foundational Models from <a href="https://aws.amazon.com/bedrock/">Amazon Bedrock</a> and <a href="https://github.com/pgvector/pgvector">pgvector</a> as Vector Engine</p>'
    st.markdown(subheader, unsafe_allow_html=True)
    image = Image.open("static/RAG_APG.png")
    st.image(image, caption='Generative AI Q&A with Amazon Bedrock, Aurora PostgreSQL and pgvector')
    
    user_question = st.text_input("Ask a question about your documents:", placeholder="What is Amazon Aurora?")

    go_button = st.button("Submit", type="secondary")
    if go_button or user_question:
        with st.spinner("Processing..."):
            handle_userinput(user_question)

    with st.sidebar:
        st.subheader("Your documents")
        pdf_docs = st.file_uploader(
            "Upload your PDFs here and click on 'Process'", type="pdf", accept_multiple_files=True)
    
        if st.button("Process"):
            with st.spinner("Processing"):
                # get pdf text
                raw_text = get_pdf_text(pdf_docs)

                # get the text chunks
                text_chunks = get_text_chunks(raw_text)

                # create vector store
                vectorstore = get_vectorstore(text_chunks)

                # create conversation chain
                st.session_state.conversation = get_conversation_chain(vectorstore)

                st.success('PDF uploaded successfully!', icon="✅")
    
    with st.sidebar:
        st.divider()

    st.sidebar.markdown(
    """
    ### Sample questions to get started:
    1. What is Amazon Aurora?
    2. How can I migrate from PostgreSQL to Aurora and the other way around?
    3. What does "three times the performance of PostgreSQL" mean?
    4. What is Aurora Standard and Aurora I/O-Optimized?
    5. How do I scale the compute resources associated with my Amazon Aurora DB Instance?
    6. How does Amazon Aurora improve my databases fault tolerance to disk failures?
    7. How does Aurora improve recovery time after a database crash?
    8. How can I improve upon the availability of a single Amazon Aurora database?
    """
)

if __name__ == '__main__':
    load_dotenv()
    
    BEDROCK_CLIENT = boto3.client("bedrock-runtime", 'us-west-2')
    
    CONNECTION_STRING = PGVector.connection_string_from_db_params(                                                  
        driver = os.environ.get("PGVECTOR_DRIVER"),
        user = os.environ.get("PGVECTOR_USER"),                                      
        password = os.environ.get("PGVECTOR_PASSWORD"),                                  
        host = os.environ.get("PGVECTOR_HOST"),                                            
        port = os.environ.get("PGVECTOR_PORT"),                                          
        database = os.environ.get("PGVECTOR_DATABASE")                                       
)  

    main()