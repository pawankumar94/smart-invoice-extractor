"""
Results display component for showing extraction results.
"""
import streamlit as st
import pandas as pd
import json
import sqlalchemy as sa
import logging
from ocr_app.db.database import get_async_session, extractions_table, schemas_table
from ocr_app.utils.async_helpers import run_async

logger = logging.getLogger(__name__)

def display_results(results):
    """Display the extraction results in a readable format"""
    if not results:
        st.markdown("""
        <div class="error-box">
            <strong>Error:</strong> No results to display
        </div>
        """, unsafe_allow_html=True)
        return
    
    if "error" in results:
        st.markdown(f"""
        <div class="error-box">
            <strong>Error:</strong> {results["error"]}
        </div>
        """, unsafe_allow_html=True)
        return
    
    # Display nicely formatted results first
    st.markdown('<div class="results-container">', unsafe_allow_html=True)
    
    # Display basic information
    st.markdown('<h2 class="results-header">Invoice Results</h2>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown('<h3>Invoice Information</h3>', unsafe_allow_html=True)
        if results.get("invoice_number"):
            st.markdown(f'<p><span class="field-label">Invoice Number:</span> <span class="field-value">{results["invoice_number"]}</span></p>', unsafe_allow_html=True)
        if results.get("invoice_date"):
            st.markdown(f'<p><span class="field-label">Invoice Date:</span> <span class="field-value">{results["invoice_date"]}</span></p>', unsafe_allow_html=True)
        if results.get("due_date") and results["due_date"] not in ["null", "NULL", None]:
            st.markdown(f'<p><span class="field-label">Due Date:</span> <span class="field-value">{results["due_date"]}</span></p>', unsafe_allow_html=True)
    
    with col2:
        st.markdown('<h3>Vendor Information</h3>', unsafe_allow_html=True)
        if results.get("vendor_name"):
            st.markdown(f'<p><span class="field-label">Vendor:</span> <span class="field-value">{results["vendor_name"]}</span></p>', unsafe_allow_html=True)
        if results.get("vendor_address"):
            # Format multi-line addresses properly
            formatted_address = results["vendor_address"].replace("\n", "<br>")
            st.markdown(f'<p><span class="field-label">Vendor Address:</span> <span class="field-value">{formatted_address}</span></p>', unsafe_allow_html=True)
    
    with col3:
        st.markdown('<h3>Customer Information</h3>', unsafe_allow_html=True)
        if results.get("customer_name"):
            st.markdown(f'<p><span class="field-label">Customer:</span> <span class="field-value">{results["customer_name"]}</span></p>', unsafe_allow_html=True)
        if results.get("customer_address"):
            # Format multi-line addresses properly
            formatted_address = results["customer_address"].replace("\n", "<br>")
            st.markdown(f'<p><span class="field-label">Customer Address:</span> <span class="field-value">{formatted_address}</span></p>', unsafe_allow_html=True)
    
    # Display line items if available
    if results.get("line_items"):
        st.markdown('<h3>Line Items</h3>', unsafe_allow_html=True)
        
        # Convert line items to DataFrame
        line_items = results["line_items"]
        if isinstance(line_items, list) and len(line_items) > 0:
            # Handle different possible structures of line items
            if all(isinstance(item, dict) for item in line_items):
                # Clean up column names for display
                df = pd.DataFrame(line_items)
                # If columns contain item and value, rename them for better display
                if 'item' in df.columns and 'value' in df.columns:
                    df = df.rename(columns={'item': 'Description', 'value': 'Amount'})
            else:
                # Try to handle alternative formats
                try:
                    formatted_items = []
                    for i, item in enumerate(line_items):
                        if isinstance(item, dict):
                            formatted_items.append(item)
                        else:
                            formatted_items.append({"Description": str(item)})
                    df = pd.DataFrame(formatted_items)
                except Exception as e:
                    st.error(f"Could not format line items: {str(e)}")
                    st.write(line_items)  # Fallback to raw display
                    df = None
            
            if df is not None:
                # Style the dataframe
                st.dataframe(df, use_container_width=True, height=min(350, (len(df) + 1) * 35 + 10))
    
    # Display totals in a nice layout
    st.markdown('<h3>Totals</h3>', unsafe_allow_html=True)
    totals_cols = st.columns([2, 1, 1])
    
    with totals_cols[2]:  # Right-aligned totals
        if results.get("subtotal"):
            st.markdown(f'<p style="text-align: right"><span class="field-label">Subtotal:</span> <span class="field-value">{results["subtotal"]}</span></p>', unsafe_allow_html=True)
        if results.get("tax_amount"):
            st.markdown(f'<p style="text-align: right"><span class="field-label">Tax:</span> <span class="field-value">{results["tax_amount"]}</span></p>', unsafe_allow_html=True)
        if results.get("total_amount"):
            st.markdown(f'<p style="text-align: right; font-weight: bold;"><span class="field-label">Total:</span> <span class="field-value">{results["total_amount"]}</span></p>', unsafe_allow_html=True)
    
    # Display currency and payment method in a separate section
    st.markdown('<h3>Payment Details</h3>', unsafe_allow_html=True)
    payment_cols = st.columns(2)
    with payment_cols[0]:
        if results.get("currency"):
            st.markdown(f'<p><span class="field-label">Currency:</span> <span class="field-value">{results["currency"]}</span></p>', unsafe_allow_html=True)
    with payment_cols[1]:
        if results.get("payment_method"):
            st.markdown(f'<p><span class="field-label">Payment Method:</span> <span class="field-value">{results["payment_method"]}</span></p>', unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Display raw JSON in an expander
    with st.expander("View Raw JSON"):
        # Pretty-print the JSON
        st.json(results)

def show_results():
    """Show extraction results"""
    st.subheader("Extraction Results")
    
    # Get extraction results directly with SQL
    try:
        async def get_extraction_results():
            async with get_async_session() as session:
                # Fix column names in query
                query = sa.select(
                    extractions_table, schemas_table.c.name.label("schema_name")
                ).join(
                    schemas_table, extractions_table.c.schema_id == schemas_table.c.id
                ).order_by(
                    extractions_table.c.created_at.desc()
                ).limit(5)
                
                result = await session.execute(query)
                return result.fetchall()
        
        extractions = run_async(get_extraction_results())
        
        if not extractions:
            st.info("No extraction results found")
        else:
            for row in extractions:
                with st.expander(f"{row.file_name} - {row.created_at}"):
                    try:
                        results = json.loads(row.result)
                        st.json(results)
                    except json.JSONDecodeError:
                        st.error("Could not parse extraction results")
    except Exception as e:
        logger.error(f"Error loading extraction results: {str(e)}")
        st.error(f"Error loading results: {str(e)}") 