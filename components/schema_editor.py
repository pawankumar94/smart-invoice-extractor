"""
Schema editor component for creating and editing extraction schemas.
"""
import streamlit as st
import json
import sqlalchemy as sa
import logging
from datetime import datetime
import time
from ocr_app.db.database import get_async_session, schemas_table
from ocr_app.utils.async_helpers import run_async

logger = logging.getLogger(__name__)

def schema_editor():
    """Create or edit a schema"""
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    st.markdown('<h2 class="subheader">Schema Editor</h2>', unsafe_allow_html=True)
    
    # Get existing schemas
    try:
        async def get_schemas():
            async with get_async_session() as session:
                query = sa.select(schemas_table).order_by(schemas_table.c.id)
                result = await session.execute(query)
                return result.fetchall()
        
        schemas = run_async(get_schemas())
        
        # Handle case when schemas is None (error occurred)
        if schemas is None:
            st.error("Could not load schemas from database. Check logs for details.")
            schemas = []  # Use empty list as fallback
            
        schema_names = ["-- Create New Schema --"] + [schema.name for schema in schemas]
        
        selected_schema_name = st.selectbox("Select Schema Template or Create New", schema_names)
        
        # Initialize empty schema
        schema_data = None
        schema_id = None
        
        if selected_schema_name != "-- Create New Schema --":
            # Load selected schema
            for schema in schemas:
                if schema.name == selected_schema_name:
                    # Convert row to dict for easier handling
                    schema_data = {
                        "id": schema.id,
                        "name": schema.name,
                        "description": schema.description,
                        "fields": json.loads(schema.fields)
                    }
                    schema_id = schema.id
                    break
    except Exception as e:
        st.error(f"Error in schema editor: {str(e)}")
        # Show minimal UI with error message
        st.warning("Schema editor is not available due to database errors.")
        return

    # Schema name and description
    schema_name = st.text_input("Schema Name", value=schema_data["name"] if schema_data else "")
    schema_description = st.text_area("Schema Description", value=schema_data["description"] if schema_data else "")
    
    # Fields section
    st.markdown('<h3>Fields</h3>', unsafe_allow_html=True)
    
    # Initialize fields from existing schema or create empty list
    if schema_data and "fields" in schema_data:
        fields = schema_data["fields"]
    else:
        fields = []
    
    # Use session state to store fields
    if "schema_fields" not in st.session_state:
        st.session_state.schema_fields = fields
    
    # Add parent and child field buttons
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Add Field", key="add_field_btn", use_container_width=True):
            st.session_state.schema_fields.append({
                "name": f"field_{len(st.session_state.schema_fields) + 1}",
                "description": "",
                "field_type": "string",
                "required": False,
                "constraints": {},
                "parent_field": None,
                "child_fields": []
            })

    with col2:
        if st.button("Add Object Field", key="add_object_field_btn", use_container_width=True):
            st.session_state.schema_fields.append({
                "name": f"object_{len(st.session_state.schema_fields) + 1}",
                "description": "Container for nested fields",
                "field_type": "object",
                "required": False,
                "constraints": {},
                "parent_field": None,
                "child_fields": []
            })

    # Get all potential parent fields (object type fields)
    parent_fields = [None] + [field["name"] for field in st.session_state.schema_fields 
                             if field["field_type"] == "object"]
    
    # Display fields with options to edit
    field_types = ["string", "number", "date", "list", "object"]
    
    fields_to_remove = []
    
    # Create a visual separator for the field list headers
    st.markdown("""
    <div class="field-header">
        <div style="flex: 3;">Name</div>
        <div style="flex: 3;">Description</div>
        <div style="flex: 2;">Type</div>
        <div style="flex: 2;">Parent</div>
        <div style="flex: 1;">Required</div>
        <div style="flex: 1;">Actions</div>
    </div>
    """, unsafe_allow_html=True)
    
    for i, field in enumerate(st.session_state.schema_fields):
        # Create container for each field with conditional styling for child fields
        parent_class = "field-child" if field.get("parent_field") else ""
        st.markdown(f'<div class="schema-field-row {parent_class}">', unsafe_allow_html=True)
        
        # Create a row for each field
        cols = st.columns([3, 3, 2, 2, 1, 1])
        
        with cols[0]:
            field["name"] = st.text_input(f"Name {i}", value=field["name"], key=f"name_{i}", 
                                         label_visibility="collapsed")
        
        with cols[1]:
            field["description"] = st.text_input(f"Description {i}", 
                                                value=field.get("description", ""), 
                                                key=f"desc_{i}",
                                                label_visibility="collapsed")
        
        with cols[2]:
            field["field_type"] = st.selectbox(f"Type {i}", field_types, 
                                             index=field_types.index(field["field_type"]) if field["field_type"] in field_types else 0,
                                             key=f"type_{i}",
                                             label_visibility="collapsed")
        
        with cols[3]:
            current_parent = field.get("parent_field")
            new_parent = st.selectbox(f"Parent {i}", parent_fields, 
                                      index=parent_fields.index(current_parent) if current_parent in parent_fields else 0,
                                      key=f"parent_{i}",
                                      label_visibility="collapsed")
            field["parent_field"] = new_parent
        
        with cols[4]:
            field["required"] = st.checkbox("", value=field.get("required", False), 
                                          key=f"req_{i}",
                                          label_visibility="collapsed")
        
        with cols[5]:
            if st.button("🗑️", key=f"remove_{i}", help="Remove this field", 
                       use_container_width=True, type="secondary"):
                fields_to_remove.append(i)
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Remove fields marked for deletion (in reverse order to maintain indices)
    for idx in sorted(fields_to_remove, reverse=True):
        del st.session_state.schema_fields[idx]
    
    # Save schema button
    if st.button("Save Schema", key="save_schema_btn"):
        if not schema_name:
            st.error("Schema name is required")
        elif len(st.session_state.schema_fields) == 0:
            st.error("At least one field is required")
        else:
            # Validate parent-child relationships
            validation_passed = True
            # Check that all parent fields exist and are objects
            for field in st.session_state.schema_fields:
                parent_name = field.get("parent_field")
                if parent_name:
                    # Find the parent field
                    parent_found = False
                    is_object = False
                    for potential_parent in st.session_state.schema_fields:
                        if potential_parent["name"] == parent_name:
                            parent_found = True
                            is_object = potential_parent["field_type"] == "object"
                            break
                    
                    if not parent_found:
                        st.error(f"Parent field '{parent_name}' not found for field '{field['name']}'")
                        validation_passed = False
                    elif not is_object:
                        st.error(f"Parent field '{parent_name}' must be an object type")
                        validation_passed = False
            
            if validation_passed:
                # Function to save schema
                async def save_schema():
                    async with get_async_session() as session:
                        try:
                            if schema_id:
                                # Update existing schema
                                update_stmt = schemas_table.update().where(
                                    schemas_table.c.id == schema_id
                                ).values(
                                    name=schema_name,
                                    description=schema_description,
                                    fields=json.dumps(st.session_state.schema_fields),
                                    updated_at=datetime.now()
                                )
                                result = await session.execute(update_stmt)
                                await session.commit()
                                return result.rowcount > 0, "update"
                            else:
                                # Create new schema
                                now = datetime.now()
                                insert_stmt = schemas_table.insert().values(
                                    name=schema_name,
                                    description=schema_description,
                                    fields=json.dumps(st.session_state.schema_fields),
                                    created_at=now,
                                    updated_at=now
                                )
                                result = await session.execute(insert_stmt)
                                await session.commit()
                                return result.lastrowid, "create"
                        except Exception as e:
                            logger.error(f"Error saving schema: {str(e)}")
                            await session.rollback()
                            return None, f"error: {str(e)}"
                
                result, operation = run_async(save_schema())
                
                if operation == "update" and result:
                    st.success("Schema updated successfully")
                elif operation == "create" and result:
                    st.success(f"Schema created successfully with ID: {result}")
                else:
                    st.error(f"Failed to {operation} schema")
                
                # Reset session state
                st.session_state.schema_fields = []
                time.sleep(1)
                st.experimental_rerun()
    
    st.markdown('</div>', unsafe_allow_html=True) 