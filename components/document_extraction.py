"""
Document extraction UI component.
"""
import base64
import json
import logging
import os
import streamlit as st
import time
from pathlib import Path
import tempfile
import sqlalchemy as sa

from ocr_app.models.gemini_model import GeminiModel
from ocr_app.schemas.base import ExtractionSchema
from ocr_app.db.database import get_async_session, schemas_table, extractions_table
from ocr_app.utils.config import get_settings
from ocr_app.components.results_display import display_results

logger = logging.getLogger(__name__)
settings = get_settings()

def save_temp_file(uploaded_file):
    """Save the uploaded file to a temporary location"""
    file_extension = os.path.splitext(uploaded_file.name)[1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as tmp_file:
        tmp_file.write(uploaded_file.getvalue())
        temp_file_path = tmp_file.name
    
    logger.info(f"Saved temp file: {temp_file_path}")
    return temp_file_path

async def process_document(uploaded_file, schema_id):
    """Process document with OCR using Gemini model"""
    try:
        # Save uploaded file to temp location
        file_path = save_temp_file(uploaded_file)
        logger.info(f"File exists: {os.path.exists(file_path)}")
        logger.info(f"File size: {os.path.getsize(file_path)} bytes")
        
        # Check environment variables are set
        if not settings.GOOGLE_APPLICATION_CREDENTIALS or not settings.VERTEX_AI_PROJECT_ID:
            logger.error("Missing required environment variables: GOOGLE_APPLICATION_CREDENTIALS or VERTEX_AI_PROJECT_ID")
            return {"error": "Missing required Google Cloud credentials. Please check your .env file."}
        
        if not os.path.exists(settings.GOOGLE_APPLICATION_CREDENTIALS):
            logger.error(f"Credentials file not found: {settings.GOOGLE_APPLICATION_CREDENTIALS}")
            return {"error": f"Credentials file not found: {settings.GOOGLE_APPLICATION_CREDENTIALS}"}
        
        # Initialize Gemini model
        model = GeminiModel()
        
        # Get schema from database
        async with get_async_session() as session:
            # Direct SQL query to get schema
            query = sa.select(schemas_table).where(schemas_table.c.id == schema_id)
            result = await session.execute(query)
            schema_row = result.fetchone()
            
            if not schema_row:
                return {"error": "Schema not found"}
            
            # Convert to schema object
            schema_obj = {
                "id": schema_row.id,
                "name": schema_row.name,
                "description": schema_row.description,
                "fields": json.loads(schema_row.fields)
            }
            
            schema = ExtractionSchema.from_dict(schema_obj)
        
        # Process document using Gemini model
        results = await model.process_document([file_path], schema)
        logger.info(f"Document processing results received")
        
        # Save results to database if successful
        if "error" not in results:
            try:
                # Insert results into extractions table
                from datetime import datetime
                now = datetime.now()
                insert_stmt = extractions_table.insert().values(
                    schema_id=schema_id,
                    file_name=uploaded_file.name,
                    file_path=file_path,
                    model_used="Gemini",
                    result=json.dumps(results),
                    created_at=now
                )
                async with get_async_session() as session:
                    await session.execute(insert_stmt)
                    await session.commit()
                logger.info("Results saved to database")
            except Exception as e:
                logger.error(f"Error saving results: {str(e)}")
                return {"error": "Failed to save results to database"}
        return results
    except Exception as e:
        logger.error(f"Error processing document: {str(e)}")
        return {"error": "Failed to process document"}

def show_document_extraction():
    """Show document extraction interface"""
    # Get all schemas directly
    try:
        async def get_schemas():
            async with get_async_session() as session:
                query = sa.select(schemas_table).order_by(schemas_table.c.id)
                result = await session.execute(query)
                return result.fetchall()
        
        from ocr_app.utils.async_helpers import run_async
        schema_rows = run_async(get_schemas())
        
        if not schema_rows:
            st.warning("No schemas found. Please create a schema in the Schema Editor tab first.")
            return
        
        schema_options = {row.name: row.id for row in schema_rows}
        selected_schema_name = st.selectbox("Select Schema", list(schema_options.keys()))
        selected_schema_id = schema_options[selected_schema_name]
    except Exception as e:
        st.error(f"Error loading schemas: {str(e)}")
        return
    
    # Upload file
    uploaded_file = st.file_uploader("Choose a file to process", type=["pdf", "jpg", "jpeg", "png"])
    
    if uploaded_file:
        # Display the uploaded file in a styled container
        st.markdown('<div class="document-preview">', unsafe_allow_html=True)
        
        if uploaded_file.type == "application/pdf":
            st.markdown('<h3 class="document-preview-header">PDF Preview</h3>', unsafe_allow_html=True)
            base64_pdf = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')
            pdf_display = f'<div class="pdf-preview"><iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="500" type="application/pdf"></iframe></div>'
            st.markdown(pdf_display, unsafe_allow_html=True)
        else:
            st.markdown('<h3 class="document-preview-header">Image Preview</h3>', unsafe_allow_html=True)
            st.markdown('<div class="image-preview">', unsafe_allow_html=True)
            st.image(uploaded_file, caption=uploaded_file.name, use_column_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Process button with improved styling
        col1, col2 = st.columns([3, 1])
        with col2:
            process_button = st.button("Process Document", use_container_width=True)
        
        # Process the document
        if process_button:
            with st.spinner("Processing document..."):
                results = run_async(process_document(uploaded_file, selected_schema_id))
                
                if results is None:
                    st.error("Error processing document - check logs for details")
                elif "error" in results:
                    st.error(f"Error processing document: {results['error']}")
                else:
                    st.success("Document processed successfully!")
                    # Display formatted results instead of raw JSON
                    display_results(results) 