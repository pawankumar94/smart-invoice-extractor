#!/usr/bin/env python3
"""
Intelligent Invoice Extraction System with Google Gemini
A Streamlit web application for extracting structured information from invoices.
"""

import os
import sys
import json
import logging
import asyncio
from pathlib import Path
from datetime import datetime

import streamlit as st
import pandas as pd

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set page configuration
st.set_page_config(
    page_title="Invoice Intelligence",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Load dependencies
from ocr_app.utils.config import get_settings
from ocr_app.db.database import initialize_db, get_async_session, schemas_table, extractions_table
from ocr_app.schemas.base import Field, ExtractionSchema
from ocr_app.models.gemini_model import GeminiModel
from ocr_app.utils.async_helpers import run_async

# Load and apply custom CSS
def load_css():
    css_file = Path(__file__).parent / "static/css/style.css"
    if css_file.exists():
        with open(css_file) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    else:
        logger.warning(f"CSS file not found: {css_file}")

# Display application header
def show_header():
    col1, col2 = st.columns([1, 4])
    
    with col1:
        st.image("https://img.icons8.com/color/96/000000/invoice--v1.png", width=100)
    
    with col2:
        st.markdown("""
        <h1 style="margin-bottom: 0px;">Invoice Intelligence</h1>
        <p style="font-size: 1.2rem; margin-top: 0px; color: var(--primary-color);">
            Extract structured data from invoices with AI
        </p>
        """, unsafe_allow_html=True)
    
    st.markdown("---")

# Setup sidebar with helpful information
def setup_sidebar():
    with st.sidebar:
        st.image("https://img.icons8.com/color/96/000000/invoice--v1.png", width=80)
        st.markdown("## Controls")
        st.markdown("---")
        
        st.markdown("### Supported Files")
        st.markdown("- PDF documents")
        st.markdown("- JPG/JPEG images")
        st.markdown("- PNG images")
        
        st.markdown("### About")
        st.markdown("""
        This application uses Google's Gemini AI to extract 
        structured data from invoice documents.
        """)
        
        st.markdown("---")
        
        if st.button("Initialize Database", use_container_width=True):
            with st.spinner("Initializing database..."):
                success = run_async(initialize_db())
                if success:
                    st.success("Database initialized successfully!")
                else:
                    st.error("Failed to initialize database")

# Document extraction UI component
def document_extraction_tab():
    st.title("Document Extraction")
    
    # Get available schemas from database
    async def get_schemas():
        async with get_async_session() as session:
            query = sa.select(schemas_table).order_by(schemas_table.c.id)
            result = await session.execute(query)
            return result.fetchall()
    
    schemas = run_async(get_schemas())
    
    if not schemas:
        st.warning("No extraction schemas found. Please create a schema in the Schema Editor tab.")
        return
    
    # Schema selection
    schema_options = {schema.name: schema.id for schema in schemas}
    schema_name = st.selectbox("Select extraction schema", options=list(schema_options.keys()))
    schema_id = schema_options[schema_name]
    
    # File upload
    st.markdown("### Upload Invoice")
    uploaded_file = st.file_uploader(
        "Choose a PDF or image file", 
        type=["pdf", "jpg", "jpeg", "png"]
    )
    
    if uploaded_file:
        # Display file preview
        st.markdown("### File Preview")
        
        if uploaded_file.type == "application/pdf":
            import base64
            base64_pdf = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')
            pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="500" type="application/pdf"></iframe>'
            st.markdown(pdf_display, unsafe_allow_html=True)
        else:
            st.image(uploaded_file, caption=uploaded_file.name, use_container_width=True)
        
        # Process button
        cols = st.columns([3, 1])
        with cols[1]:
            process_button = st.button("Extract Data", type="primary", use_container_width=True)
            
        if process_button:
            with st.spinner("Processing invoice..."):
                # Save uploaded file to temp location
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as tmp_file:
                    tmp_file.write(uploaded_file.getvalue())
                    file_path = tmp_file.name
                
                # Get schema details from database
                async def get_schema(schema_id):
                    import sqlalchemy as sa
                    async with get_async_session() as session:
                        query = sa.select(schemas_table).where(schemas_table.c.id == schema_id)
                        result = await session.execute(query)
                        return result.fetchone()
                
                schema_row = run_async(get_schema(schema_id))
                
                if not schema_row:
                    st.error("Schema not found")
                    return
                
                # Convert to schema object
                schema_obj = {
                    "id": schema_row.id,
                    "name": schema_row.name,
                    "description": schema_row.description,
                    "fields": json.loads(schema_row.fields)
                }
                schema = ExtractionSchema.from_dict(schema_obj)
                
                # Process with Gemini model
                model = GeminiModel()
                
                async def process_with_model():
                    return await model.process_document([file_path], schema)
                
                result = run_async(process_with_model())
                
                if result and "error" not in result:
                    # Save to database
                    async def save_result():
                        import sqlalchemy as sa
                        async with get_async_session() as session:
                            query = extractions_table.insert().values(
                                schema_id=schema_id,
                                file_name=uploaded_file.name,
                                file_path=file_path,
                                model_used="Gemini",
                                result=json.dumps(result),
                                created_at=datetime.now()
                            )
                            await session.execute(query)
                            await session.commit()
                    
                    run_async(save_result())
                    
                    st.success("Data extracted successfully!")
                    
                    # Display results
                    display_extraction_results(result)
                else:
                    error_msg = result.get("error", "Unknown error") if result else "Failed to process document"
                    st.error(f"Error: {error_msg}")

# Schema editor UI component                    
def schema_editor_tab():
    st.title("Schema Editor")
    
    # Get existing schemas
    async def get_schemas():
        import sqlalchemy as sa
        async with get_async_session() as session:
            query = sa.select(schemas_table).order_by(schemas_table.c.id)
            result = await session.execute(query)
            return result.fetchall()
    
    schemas = run_async(get_schemas())
    
    # Initialize session state for schema editing
    if "current_schema" not in st.session_state:
        st.session_state.current_schema = None
    
    if "schema_name" not in st.session_state:
        st.session_state.schema_name = ""
    
    if "schema_description" not in st.session_state:
        st.session_state.schema_description = ""
    
    if "fields" not in st.session_state:
        st.session_state.fields = []
    
    if "schema_id" not in st.session_state:
        st.session_state.schema_id = None
        
    if "json_editor_content" not in st.session_state:
        st.session_state.json_editor_content = ""
        
    if "json_error" not in st.session_state:
        st.session_state.json_error = None
        
    if "advanced_mode" not in st.session_state:
        st.session_state.advanced_mode = True
    
    # Two columns for schema selection and metadata
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.markdown("### Schema Selection")
        # Schema selection dropdown
        schema_names = ["-- Create New Schema --"] + [schema.name for schema in schemas] if schemas else ["-- Create New Schema --"]
        selected_schema = st.selectbox("Select a schema to edit or create new", schema_names)
        
        # Initialize schema data when selection changes
        if selected_schema != st.session_state.current_schema:
            st.session_state.current_schema = selected_schema
            
            if selected_schema != "-- Create New Schema --":
                # Find selected schema
                for schema in schemas:
                    if schema.name == selected_schema:
                        schema_data = {
                            "id": schema.id, 
                            "name": schema.name,
                            "description": schema.description,
                            "fields": json.loads(schema.fields)
                        }
                        st.session_state.schema_id = schema.id
                        st.session_state.schema_name = schema.name
                        st.session_state.schema_description = schema.description
                        st.session_state.fields = schema_data["fields"]
                        
                        # Convert internal format to advanced format with named parents and children
                        if st.session_state.advanced_mode:
                            advanced_schema = convert_to_advanced_schema(st.session_state.fields)
                            st.session_state.json_editor_content = json.dumps(advanced_schema, indent=2)
                        else:
                            # Create JSON representation in simple format
                            st.session_state.json_editor_content = json.dumps(
                                [{"name": f["name"], 
                                  "description": f.get("description", ""), 
                                  "type": f["field_type"],
                                  "required": f.get("required", False),
                                  "parent": f.get("parent_id", None)
                                 } for f in schema_data["fields"]], 
                                indent=2
                            )
                        break
            else:
                # Reset for new schema
                st.session_state.schema_id = None
                st.session_state.schema_name = ""
                st.session_state.schema_description = ""
                st.session_state.fields = []
                
                # Initialize with a template in the advanced format
                if st.session_state.advanced_mode:
                    st.session_state.json_editor_content = json.dumps([
                        {
                            "name": "Invoice Details",
                            "description": "Main container for basic invoice information",
                            "type": "object",
                            "required": True,
                            "parent": None,
                            "children": [
                                {
                                    "name": "Invoice Number",
                                    "description": "Unique identifier for the invoice",
                                    "type": "string",
                                    "required": True,
                                    "parent": "Invoice Details"
                                },
                                {
                                    "name": "Invoice Date",
                                    "description": "Date when invoice was created",
                                    "type": "date",
                                    "required": True,
                                    "parent": "Invoice Details"
                                }
                            ]
                        },
                        {
                            "name": "Vendor Information",
                            "description": "Container for vendor details",
                            "type": "object",
                            "required": True,
                            "parent": None,
                            "children": [
                                {
                                    "name": "Vendor Name",
                                    "description": "Name of the vendor",
                                    "type": "string",
                                    "required": True,
                                    "parent": "Vendor Information"
                                }
                            ]
                        }
                    ], indent=2)
                else:
                    # Simple format for new schema
                    st.session_state.json_editor_content = json.dumps([
                        {
                            "name": "invoice_number",
                            "description": "Invoice identifier",
                            "type": "string",
                            "required": True,
                            "parent": None
                        },
                        {
                            "name": "vendor_information",
                            "description": "Container for vendor details",
                            "type": "object",
                            "required": True,
                            "parent": None
                        },
                        {
                            "name": "vendor_name",
                            "description": "Name of the vendor/supplier",
                            "type": "string",
                            "required": True,
                            "parent": 1
                        }
                    ], indent=2)
    
    with col2:
        st.markdown("### Schema Details")
        # Schema name and description
        st.session_state.schema_name = st.text_input("Schema Name", value=st.session_state.schema_name)
        st.session_state.schema_description = st.text_input(
            "Schema Description", 
            value=st.session_state.schema_description,
            help="A brief description of what this schema is used for"
        )
        
        # Toggle for advanced mode
        st.session_state.advanced_mode = st.toggle(
            "Advanced Schema Mode (with named parents and children collections)", 
            value=st.session_state.advanced_mode,
            help="Use the advanced schema format with named parent references and children collections"
        )
    
    # Main schema editor area with tabs
    tab1, tab2 = st.tabs(["JSON Editor", "Visual Editor"])
    
    with tab1:
        st.markdown("### Define Your Schema")
        
        if st.session_state.advanced_mode:
            st.markdown("""
            Define your extraction schema below in JSON format. Each field should include:
            - **name**: The field name (required)
            - **description**: Brief description of the field
            - **type**: Field type (string, number, date, object, list/array)
            - **required**: Whether the field is required (true/false)
            - **parent**: Name of the parent object or null for top-level fields
            - **children**: For object fields, an array of child fields
            """)
        else:
            st.markdown("""
            Define your extraction schema below in JSON format. Each field should include:
            - **name**: The field name (required)
            - **description**: Brief description of the field
            - **type**: Field type (string, number, date, object, list)
            - **required**: Whether the field is required (true/false)
            - **parent**: For nested fields, the index of the parent object (0-based, or null for top-level)
            """)
        
        # JSON Editor
        json_content = st.text_area(
            "Schema JSON", 
            value=st.session_state.json_editor_content,
            height=400,
            help="Edit your schema in JSON format",
            key="json_editor"
        )
        
        # Validate and parse JSON
        if json_content != st.session_state.json_editor_content:
            st.session_state.json_editor_content = json_content
            try:
                parsed_fields = json.loads(json_content)
                
                # Convert to our internal format
                if st.session_state.advanced_mode:
                    new_fields = convert_from_advanced_schema(parsed_fields)
                else:
                    # Simple format conversion
                    new_fields = []
                    for i, field in enumerate(parsed_fields):
                        if not isinstance(field, dict) or "name" not in field or "type" not in field:
                            raise ValueError(f"Field {i} must have at least 'name' and 'type' properties")
                        
                        new_fields.append({
                            "name": field["name"],
                            "description": field.get("description", ""),
                            "field_type": field.get("type", "string"),
                            "required": field.get("required", False),
                            "parent_id": field.get("parent", None)
                        })
                
                st.session_state.fields = new_fields
                st.session_state.json_error = None
            except Exception as e:
                st.session_state.json_error = str(e)
                st.error(f"JSON Error: {e}")
    
    with tab2:
        st.markdown("### Visual Schema Editor")
        
        if st.session_state.fields:
            # Create a table view of the fields
            schema_rows = []
            
            # Process fields to build the visual representation
            for i, field in enumerate(st.session_state.fields):
                parent_id = field.get("parent_id")
                parent_name = ""
                
                if parent_id is not None:
                    # Find parent name if it exists
                    try:
                        if isinstance(parent_id, int) and 0 <= parent_id < len(st.session_state.fields):
                            parent_name = st.session_state.fields[parent_id]["name"]
                        elif isinstance(parent_id, str):
                            # Handle string-based parent references
                            parent_name = parent_id
                    except (IndexError, KeyError):
                        parent_name = f"Unknown ({parent_id})"
                
                schema_rows.append({
                    "Field Name": field["name"],
                    "Description": field.get("description", ""),
                    "Type": field["field_type"],
                    "Parent": parent_name,
                    "Required": "✓" if field.get("required", False) else ""
                })
            
            schema_df = pd.DataFrame(schema_rows)
            
            # Add indentation for nested fields to show hierarchy
            schema_df["Hierarchy"] = schema_df.apply(
                lambda row: "→ " + row["Field Name"] if row["Parent"] else row["Field Name"], 
                axis=1
            )
            
            # Reorder columns for better display
            display_df = schema_df[["Hierarchy", "Description", "Type", "Parent", "Required"]]
            
            # Display the schema as a styled table
            st.dataframe(
                display_df, 
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Hierarchy": st.column_config.TextColumn("Field Name"),
                    "Description": st.column_config.TextColumn("Description"),
                    "Type": st.column_config.TextColumn("Type"),
                    "Parent": st.column_config.TextColumn("Parent"),
                    "Required": st.column_config.TextColumn("Required"),
                }
            )
        else:
            st.info("No fields defined yet. Use the JSON Editor to add fields.")
    
    # Schema Preview
    with st.expander("Schema Preview", expanded=True):
        if st.session_state.fields:
            # Create a visual representation of the schema
            st.markdown("### Schema Structure")
            
            # Create a tree-like structure
            def build_schema_tree(fields, parent_id=None, level=0):
                tree = ""
                for i, field in enumerate(fields):
                    if (isinstance(parent_id, int) and field.get("parent_id") == parent_id) or \
                       (isinstance(parent_id, str) and field.get("parent_id") == parent_id):
                        indent = "  " * level
                        field_type = field["field_type"]
                        required = "required" if field.get("required", False) else "optional"
                        icon = "📦" if field_type == "object" else "📄" if field_type == "string" else "🔢" if field_type == "number" else "📅" if field_type == "date" else "📋" if field_type in ["list", "array"] else "❓"
                        
                        tree += f"{indent}{icon} **{field['name']}** ({field_type}, {required})"
                        if field.get("description"):
                            tree += f": {field['description']}\n"
                        else:
                            tree += "\n"
                        
                        # If this is an object, recursively add its children
                        if field_type == "object":
                            tree += build_schema_tree(fields, i, level + 1)
                return tree
            
            schema_tree = build_schema_tree(st.session_state.fields)
            st.markdown(schema_tree)
            
            # Display a JSON example of what would be extracted
            st.markdown("### Example Extraction Output")
            
            # Build an example JSON based on the schema
            def build_example_json(fields, parent_id=None):
                result = {}
                for i, field in enumerate(fields):
                    if field.get("parent_id") == parent_id:
                        field_type = field["field_type"]
                        field_name = field["name"]
                        
                        if field_type == "string":
                            result[field_name] = "Example value"
                        elif field_type == "number":
                            result[field_name] = 123.45
                        elif field_type == "date":
                            result[field_name] = "2025-03-25"
                        elif field_type == "object":
                            result[field_name] = build_example_json(fields, i)
                        elif field_type in ["list", "array"]:
                            result[field_name] = [{"item": "Example item", "value": 123.45}]
                return result
            
            example_json = build_example_json(st.session_state.fields)
            st.json(example_json)
    
    # Save schema button
    if st.button("Save Schema", type="primary"):
        if not st.session_state.schema_name:
            st.error("Schema name is required")
        elif not st.session_state.fields:
            st.error("At least one field is required")
        elif st.session_state.json_error:
            st.error(f"Please fix the JSON errors before saving: {st.session_state.json_error}")
        else:
            # Save schema to database
            async def save_schema():
                import sqlalchemy as sa
                try:
                    async with get_async_session() as session:
                        now = datetime.now()
                        
                        if st.session_state.schema_id:
                            # Update existing schema
                            query = schemas_table.update().where(
                                schemas_table.c.id == st.session_state.schema_id
                            ).values(
                                name=st.session_state.schema_name,
                                description=st.session_state.schema_description,
                                fields=json.dumps(st.session_state.fields),
                                updated_at=now
                            )
                            await session.execute(query)
                            await session.commit()
                            return True, "Schema updated successfully"
                        else:
                            # Create new schema
                            query = schemas_table.insert().values(
                                name=st.session_state.schema_name,
                                description=st.session_state.schema_description,
                                fields=json.dumps(st.session_state.fields),
                                created_at=now,
                                updated_at=now
                            )
                            result = await session.execute(query)
                            await session.commit()
                            return True, "Schema created successfully"
                except Exception as e:
                    logger.error(f"Error saving schema: {str(e)}")
                    return False, f"Error: {str(e)}"
            
            success, message = run_async(save_schema())
            
            if success:
                st.success(message)
                # Reset session state
                st.session_state.fields = []
                st.session_state.schema_name = ""
                st.session_state.schema_description = ""
                st.session_state.schema_id = None
                st.session_state.current_schema = None
                st.session_state.json_editor_content = ""
                st.session_state.json_error = None
                # Use the modern rerun method instead of experimental_rerun
                st.rerun()
            else:
                st.error(message)

# Helper function to convert from internal format to advanced schema format
def convert_to_advanced_schema(fields):
    # Step 1: Create a mapping of field indices to names for parent references
    field_index_to_name = {i: field["name"] for i, field in enumerate(fields)}
    
    # Step 2: Group fields by parent_id to identify children
    children_by_parent = {}
    for i, field in enumerate(fields):
        parent_id = field.get("parent_id")
        if parent_id is not None:
            if parent_id not in children_by_parent:
                children_by_parent[parent_id] = []
            
            # Make a copy of the field
            child_field = field.copy()
            
            # Replace numeric parent_id with parent name
            if isinstance(parent_id, int) and parent_id in field_index_to_name:
                child_field["parent"] = field_index_to_name[parent_id]
            else:
                child_field["parent"] = parent_id
                
            # Remove parent_id from the copy
            if "parent_id" in child_field:
                del child_field["parent_id"]
            
            # Transform field_type to type
            if "field_type" in child_field:
                child_field["type"] = child_field.pop("field_type")
                
            children_by_parent[parent_id].append(child_field)
    
    # Step 3: Create top-level objects with children
    result = []
    for i, field in enumerate(fields):
        if field.get("parent_id") is None:
            # Create a copy of the top-level field
            new_field = field.copy()
            
            # Transform field_type to type
            if "field_type" in new_field:
                new_field["type"] = new_field.pop("field_type")
                
            # Set parent to null
            new_field["parent"] = None
                
            # Remove parent_id if present
            if "parent_id" in new_field:
                del new_field["parent_id"]
            
            # Add children array if this field has children
            if i in children_by_parent:
                new_field["children"] = children_by_parent[i]
            
            result.append(new_field)
    
    return result

# Helper function to convert from advanced schema format to internal format
def convert_from_advanced_schema(advanced_schema):
    result = []
    field_name_to_index = {}  # To map parent names to indices
    
    # First pass: add all objects to our result list
    for obj in advanced_schema:
        if not isinstance(obj, dict) or "name" not in obj or "type" not in obj:
            raise ValueError(f"Each field must have at least 'name' and 'type' properties")
        
        # Create the field in our internal format
        field = {
            "name": obj["name"],
            "description": obj.get("description", ""),
            "field_type": obj["type"],
            "required": obj.get("required", False),
            "parent_id": None  # Top-level objects have no parent
        }
        
        # Add to our result and keep track of index
        field_index = len(result)
        result.append(field)
        field_name_to_index[obj["name"]] = field_index
    
    # Second pass: add all children recursively
    def process_children(children, parent_field_name):
        parent_index = field_name_to_index[parent_field_name]
        
        for child in children:
            # Create the child field
            field = {
                "name": child["name"],
                "description": child.get("description", ""),
                "field_type": child["type"],
                "required": child.get("required", False),
                "parent_id": parent_index
            }
            
            # Add to our result and keep track of index
            field_index = len(result)
            result.append(field)
            field_name_to_index[child["name"]] = field_index
            
            # Process any children of this child
            if child.get("type") == "object" and "children" in child and isinstance(child["children"], list):
                process_children(child["children"], child["name"])
    
    # Process all top-level objects with children
    for obj in advanced_schema:
        if obj.get("type") == "object" and "children" in obj and isinstance(obj["children"], list):
            process_children(obj["children"], obj["name"])
    
    return result

# Results history UI component
def results_tab():
    st.markdown('<h1 style="font-size: 1.8rem; font-weight: 600; margin-bottom: 1.5rem; color: #333; border-bottom: 2px solid #eef1ff; padding-bottom: 0.5rem;">Extraction History</h1>', unsafe_allow_html=True)
    
    # Get extraction history
    async def get_history():
        import sqlalchemy as sa
        async with get_async_session() as session:
            query = sa.select(
                extractions_table, schemas_table.c.name.label("schema_name")
            ).join(
                schemas_table, extractions_table.c.schema_id == schemas_table.c.id
            ).order_by(
                extractions_table.c.created_at.desc()
            ).limit(10)
            
            result = await session.execute(query)
            return result.fetchall()
    
    extractions = run_async(get_history())
    
    if not extractions:
        st.info("No extraction history found. Process some invoices to see results here.")
    else:
        # Initialize all session state variables for extractions
        for i, extraction in enumerate(extractions):
            view_key = f"view_extraction_{i}"
            if view_key not in st.session_state:
                st.session_state[view_key] = False
        
        # Display each extraction
        for i, extraction in enumerate(extractions):
            view_key = f"view_extraction_{i}"
            btn_key = f"btn_extraction_{i}"
            hide_btn_key = f"hide_btn_{i}"
            
            file_date = extraction.created_at.strftime("%Y-%m-%d %H:%M:%S")
            st.markdown(f'<div style="background-color: #eef1ff; padding: 0.75rem 1rem; border-radius: 8px; margin-top: 1rem; margin-bottom: 0.75rem; border-left: 3px solid #4361ee;"><h3 style="font-size: 1.1rem; font-weight: 500; color: #333; margin: 0;">{extraction.file_name} - {file_date}</h3></div>', unsafe_allow_html=True)
            
            if not st.session_state[view_key]:
                if st.button(f"Show Results", key=btn_key):
                    st.session_state[view_key] = True
                    st.rerun()
            else:
                if st.button(f"Hide Results", key=hide_btn_key):
                    st.session_state[view_key] = False
                    st.rerun()
                
                try:
                    result = json.loads(extraction.result)
                    # Display the content directly
                    display_extraction_results(result)
                except Exception as e:
                    st.error(f"Error displaying result: {str(e)}")
            
            st.markdown("---")

# Helper to display extraction results
def display_extraction_results(result):
    # Display in a structured format
    if not result:
        st.error("No results available")
        return
    
    # Success message
    st.success("Data extracted successfully!")
    
    # Function to format complex values (objects, arrays) into readable format
    def format_complex_value(value):
        if isinstance(value, dict):
            # Format dictionary nicely
            formatted_parts = []
            for k, v in value.items():
                if v is not None and v != "":
                    formatted_key = k.replace("_", " ").title()
                    formatted_parts.append(f"{formatted_key}: {v}")
            return ", ".join(formatted_parts)
        elif isinstance(value, list) and not all(isinstance(item, dict) for item in value):
            # For simple lists (not of dictionaries)
            return ", ".join(str(item) for item in value)
        return value
    
    # Track which fields we've already displayed to avoid duplication
    displayed_fields = set()
    
    # Function to determine if a field contains duplicate information
    def is_duplicate_field(field_name, field_value, data_dict):
        # Check if this is a duplicate of information already in a nested structure
        field_name_lower = field_name.lower()
        
        # For nested objects, check if their data is duplicated elsewhere
        if isinstance(field_value, dict):
            for key in data_dict:
                # Skip self-comparison
                if key == field_name:
                    continue
                
                # Check if this is a parent container that duplicates the information
                if isinstance(data_dict[key], dict) and any(
                    k.lower() in field_name_lower or field_name_lower in k.lower() 
                    for k in data_dict[key].keys()
                ):
                    return True
                    
            # It's not a duplicate
            return False
        
        # For simple fields, check if they're duplicated in a nested object
        for key, value in data_dict.items():
            if key == field_name:
                continue
                
            if isinstance(value, dict):
                # Check if this field appears as a key in any dictionary
                if any(k.lower() == field_name_lower for k in value.keys()):
                    return True
                    
        # No duplicates found
        return False
    
    # Identify categories of data
    invoice_data = {}
    vendor_data = {}
    customer_data = {}
    payment_data = {}
    line_items_data = None
    other_data = {}
    
    # Helper to normalize keys for better categorization
    def normalize_key(key):
        return key.lower().replace("_", " ")
    
    # First pass: Identify all objects to better categorize
    address_fields = set()
    
    for key, value in result.items():
        normalized_key = normalize_key(key)
        
        # Identify address fields for special handling
        if ("address" in normalized_key or 
            any(term in normalized_key for term in ["street", "city", "state", "postal code", "zip", "country"])):
            address_fields.add(key)
    
    # Second pass: Extract and categorize data
    for key, value in result.items():
        normalized_key = normalize_key(key)
        
        # Skip if already processed as part of an address
        if key in displayed_fields:
            continue
            
        # Extract line items (special handling)
        if "line item" in normalized_key or key.lower() == "line_items":
            line_items_data = value
            displayed_fields.add(key)
            continue
            
        # Handle address objects specially
        if key in address_fields:
            if "vendor" in normalized_key or "supplier" in normalized_key or "seller" in normalized_key:
                vendor_data[key] = value
            elif "customer" in normalized_key or "buyer" in normalized_key or "client" in normalized_key:
                customer_data[key] = value
            else:
                other_data[key] = value
            displayed_fields.add(key)
            continue
            
        # Process nested objects
        if isinstance(value, dict):
            # Mark all keys in this object as displayed to avoid duplicates
            for sub_key in value.keys():
                displayed_fields.add(sub_key)
                
            # Categorize by name patterns
            if any(term in normalized_key for term in ["invoice", "number", "date", "currency", "total", "subtotal", "tax"]):
                invoice_data[key] = value
            elif any(term in normalized_key for term in ["vendor", "supplier", "seller"]):
                vendor_data[key] = value
            elif any(term in normalized_key for term in ["customer", "buyer", "client"]):
                customer_data[key] = value
            elif any(term in normalized_key for term in ["payment", "account", "bank"]):
                payment_data[key] = value
            else:
                other_data[key] = value
            
            displayed_fields.add(key)
            continue
            
        # Process flat fields
        if any(term in normalized_key for term in ["invoice", "number", "date", "currency", "total", "subtotal", "tax"]):
            invoice_data[key] = value
        elif any(term in normalized_key for term in ["vendor", "supplier", "seller"]):
            vendor_data[key] = value
        elif any(term in normalized_key for term in ["customer", "buyer", "client"]):
            customer_data[key] = value
        elif any(term in normalized_key for term in ["payment", "account", "bank"]):
            payment_data[key] = value
        else:
            other_data[key] = value
        
        displayed_fields.add(key)
    
    # Final deduplication pass: Remove fields that are duplicated in nested objects
    for category_dict in [invoice_data, vendor_data, customer_data, payment_data, other_data]:
        keys_to_remove = []
        
        for key, value in category_dict.items():
            if is_duplicate_field(key, value, category_dict):
                keys_to_remove.append(key)
                
        for key in keys_to_remove:
            category_dict.pop(key)
            
    # Helper function to display a dictionary field in a prettier format
    def display_pretty_dict(data, field_name):
        st.markdown(f"**{field_name}:**")
        
        # Create a bullet list of key-value pairs
        for k, v in data.items():
            if v is not None and v != "" and v != "None":
                formatted_key = k.replace("_", " ").title()
                
                # If it's a nested dictionary, handle recursively with indentation
                if isinstance(v, dict):
                    st.markdown(f"- **{formatted_key}**:")
                    for sub_k, sub_v in v.items():
                        if sub_v is not None and sub_v != "" and sub_v != "None":
                            formatted_sub_key = sub_k.replace("_", " ").title()
                            st.markdown(f"  - **{formatted_sub_key}:** {sub_v}")
                else:
                    st.markdown(f"- **{formatted_key}:** {v}")
    
    # Create separate sections based on data categories
    # 1. Display Invoice Information
    if invoice_data:
        st.markdown("### Invoice Information")
        for key, value in invoice_data.items():
            if value is not None and value != "":
                formatted_key = key.replace("_", " ").title()
                if isinstance(value, dict):
                    # Use the pretty display for nested objects
                    display_pretty_dict(value, formatted_key)
                else:
                    st.markdown(f"**{formatted_key}:** {format_complex_value(value)}")
    
    # 2. Display Vendor Details
    if vendor_data:
        st.markdown("### Vendor Details")
        
        # Specially handle address fields for better display
        vendor_address_dict = {}
        other_vendor_fields = {}
        
        # Separate address fields from other vendor fields
        for key, value in vendor_data.items():
            if "address" in key.lower():
                if isinstance(value, dict):
                    vendor_address_dict = value  # Use the structured address
                else:
                    # If it's a string, add it as a separate field
                    other_vendor_fields[key] = value
            else:
                other_vendor_fields[key] = value
        
        # Display non-address vendor fields first
        for key, value in other_vendor_fields.items():
            if value is not None and value != "":
                formatted_key = key.replace("_", " ").title()
                if isinstance(value, dict):
                    # Use the pretty display for nested objects
                    display_pretty_dict(value, formatted_key)
                else:
                    st.markdown(f"**{formatted_key}:** {format_complex_value(value)}")
        
        # Display address in a nice formatted box if we have it
        if vendor_address_dict:
            st.markdown("### Vendor Address")
            # Create a nice styled box for the address
            with st.container():
                st.markdown("""
                <style>
                .address-box {
                    background-color: #f0f2f6;
                    border-radius: 10px;
                    padding: 15px;
                }
                </style>
                """, unsafe_allow_html=True)
                
                with st.container():
                    st.markdown('<div class="address-box">', unsafe_allow_html=True)
                    cols = st.columns(2)
                    
                    # Map common address fields to their display labels
                    address_fields_map = {
                        "street": "Street",
                        "city": "City",
                        "state": "State",
                        "postal_code": "Postal Code",
                        "zip": "ZIP",
                        "country": "Country"
                    }
                    
                    # Display each address component in the appropriate column
                    for i, (sub_key, sub_value) in enumerate(vendor_address_dict.items()):
                        if sub_value is not None and sub_value != "" and sub_value != "None":
                            # Try to map to a standard field name, or use the key itself
                            normalized_key = sub_key.lower().replace("_", "")
                            display_key = None
                            
                            for k, v in address_fields_map.items():
                                if k in normalized_key:
                                    display_key = v
                                    break
                            
                            if not display_key:
                                display_key = sub_key.replace("_", " ").title()
                            
                            col_idx = 0 if i % 2 == 0 or "street" in normalized_key else 1
                            with cols[col_idx]:
                                st.markdown(f"**{display_key}**: {sub_value}")
                    
                    st.markdown('</div>', unsafe_allow_html=True)
    
    # 3. Display Customer Information
    if customer_data:
        st.markdown("### Customer Information")
        
        # Specially handle address fields for better display
        customer_address_dict = {}
        other_customer_fields = {}
        
        # Separate address fields from other customer fields
        for key, value in customer_data.items():
            if "address" in key.lower():
                if isinstance(value, dict):
                    customer_address_dict = value  # Use the structured address
                else:
                    # If it's a string, add it as a separate field
                    other_customer_fields[key] = value
            else:
                other_customer_fields[key] = value
        
        # Display non-address customer fields first
        for key, value in other_customer_fields.items():
            if value is not None and value != "":
                formatted_key = key.replace("_", " ").title()
                if isinstance(value, dict):
                    # Use the pretty display for nested objects
                    display_pretty_dict(value, formatted_key)
                else:
                    st.markdown(f"**{formatted_key}:** {format_complex_value(value)}")
        
        # Display address in a nice formatted box if we have it
        if customer_address_dict and any(v is not None and v != "" and v != "None" for v in customer_address_dict.values()):
            st.markdown("### Customer Address")
            # Create a nice styled box for the address
            with st.container():
                with st.container():
                    st.markdown('<div class="address-box">', unsafe_allow_html=True)
                    cols = st.columns(2)
                    
                    # Map common address fields to their display labels
                    address_fields_map = {
                        "street": "Street",
                        "city": "City",
                        "state": "State",
                        "postal_code": "Postal Code",
                        "zip": "ZIP",
                        "country": "Country"
                    }
                    
                    # Display each address component in the appropriate column
                    for i, (sub_key, sub_value) in enumerate(customer_address_dict.items()):
                        if sub_value is not None and sub_value != "" and sub_value != "None":
                            # Try to map to a standard field name, or use the key itself
                            normalized_key = sub_key.lower().replace("_", "")
                            display_key = None
                            
                            for k, v in address_fields_map.items():
                                if k in normalized_key:
                                    display_key = v
                                    break
                            
                            if not display_key:
                                display_key = sub_key.replace("_", " ").title()
                            
                            col_idx = 0 if i % 2 == 0 or "street" in normalized_key else 1
                            with cols[col_idx]:
                                st.markdown(f"**{display_key}**: {sub_value}")
                    
                    st.markdown('</div>', unsafe_allow_html=True)
    
    # 4. Display Payment Details
    if payment_data:
        st.markdown("### Payment Details")
        for key, value in payment_data.items():
            if value is not None and value != "":
                formatted_key = key.replace("_", " ").title()
                if isinstance(value, dict):
                    # Use the pretty display for nested objects
                    display_pretty_dict(value, formatted_key)
                else:
                    st.markdown(f"**{formatted_key}:** {format_complex_value(value)}")
    
    # 5. Display Other Information
    if other_data:
        st.markdown("### Additional Information")
        for key, value in other_data.items():
            if value is not None and value != "":
                formatted_key = key.replace("_", " ").title()
                if isinstance(value, dict):
                    # Use the pretty display for nested objects
                    display_pretty_dict(value, formatted_key)
                else:
                    st.markdown(f"**{formatted_key}:** {format_complex_value(value)}")
    
    # 6. Display Line Items
    if line_items_data:
        st.markdown("### Line Items")
        try:
            if isinstance(line_items_data, list):
                # If line items are properly structured (list of dicts)
                if all(isinstance(item, dict) for item in line_items_data):
                    df = pd.DataFrame(line_items_data)
                    st.dataframe(df, use_container_width=True)
                # If line items are simple strings or mixed types
                else:
                    for i, item in enumerate(line_items_data, 1):
                        if isinstance(item, dict):
                            item_desc = ", ".join(f"{k}: {v}" for k, v in item.items())
                            st.markdown(f"{i}. {item_desc}")
                        else:
                            st.markdown(f"{i}. {item}")
        except Exception as e:
            st.error(f"Error displaying line items: {str(e)}")
            st.json(line_items_data)  # Fallback to raw JSON
    
    # Show raw JSON in an expander
    with st.expander("Raw Data"):
        st.json(result)

# Default schema creation 
async def ensure_default_schema():
    """Create a default schema if none exists"""
    import sqlalchemy as sa
    
    async with get_async_session() as session:
        # Check if schemas exist
        query = sa.select(sa.func.count()).select_from(schemas_table)
        result = await session.execute(query)
        count = result.scalar()
        
        if count == 0:
            # Create default schema
            logger.info("Creating default invoice schema")
            
            invoice_fields = [
                Field(name="invoice_number", description="The invoice identifier", field_type="string").dict(),
                Field(name="invoice_date", description="Date the invoice was issued", field_type="date").dict(),
                Field(name="due_date", description="Date payment is due", field_type="date").dict(),
                Field(name="vendor_name", description="Name of the vendor/supplier", field_type="string").dict(),
                Field(name="vendor_address", description="Address of the vendor", field_type="string").dict(),
                Field(name="customer_name", description="Name of the customer", field_type="string").dict(),
                Field(name="customer_address", description="Address of the customer", field_type="string").dict(),
                Field(name="line_items", description="Products or services provided", field_type="list").dict(),
                Field(name="subtotal", description="Sum of all line items before tax", field_type="number").dict(),
                Field(name="tax_amount", description="Tax applied to the invoice", field_type="number").dict(),
                Field(name="total_amount", description="Total amount due including tax", field_type="number").dict(),
                Field(name="currency", description="Currency used in the invoice", field_type="string").dict(),
                Field(name="payment_method", description="Method of payment", field_type="string").dict(),
            ]
            
            # Insert schema
            now = datetime.now()
            query = schemas_table.insert().values(
                name="Standard Invoice",
                description="Default schema for extracting common invoice fields",
                fields=json.dumps(invoice_fields),
                created_at=now,
                updated_at=now
            )
            await session.execute(query)
            await session.commit()
            return True
        
        return True

# Main application
def main():
    # Load CSS first
    load_css()
    
    # Initialize database
    db_initialized = run_async(initialize_db())
    if not db_initialized:
        st.warning("⚠️ Failed to initialize database. Some features may not work.")
    
    # Create default schema if needed
    schema_created = run_async(ensure_default_schema())
    if not schema_created:
        st.warning("⚠️ Failed to create default schema. Please create one manually.")
    
    # Display header and sidebar
    show_header()
    setup_sidebar()
    
    # Create tabs
    tab1, tab2, tab3 = st.tabs([
        "📄 Document Extraction", 
        "📝 Schema Editor", 
        "📋 Extraction History"
    ])
    
    # Fill tabs with content
    with tab1:
        document_extraction_tab()
    
    with tab2:
        schema_editor_tab()
    
    with tab3:
        results_tab()

if __name__ == "__main__":
    # Fix for missing sqlalchemy import
    import sqlalchemy as sa
    main() 