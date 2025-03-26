import json
import os
import base64
import logging
import mimetypes
from typing import List, Dict, Any, Optional, Union
from pathlib import Path

import vertexai
from vertexai.generative_models import GenerativeModel, Part

from ocr_app.schemas.base import ExtractionSchema
from ocr_app.utils.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

class GeminiModel:
    """Interface to Google's Gemini model for document processing"""
    
    def __init__(self):
        """Initialize Gemini model"""
        credentials_path = settings.GOOGLE_APPLICATION_CREDENTIALS
        project_id = settings.VERTEX_AI_PROJECT_ID
        location = settings.VERTEX_AI_LOCATION
        
        if credentials_path and os.path.exists(credentials_path):
            logger.info(f"Using service account from: {credentials_path}")
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
        
        logger.info(f"Initialized Vertex AI with project: {project_id}, location: {location}")
        
        # Initialize Vertex AI
        vertexai.init(project=project_id, location=location)
        
        # Initialize model parameters - ensure all parameters are proper types
        self.generation_config = {
            "max_output_tokens": 2048,
            "temperature": 0.0,  # Ensure this is a float
            "top_p": 0.95,       # Ensure this is a float
            "top_k": 40          # Ensure this is an int
        }
        
        # Create the model
        model_name = settings.GEMINI_MODEL
        logger.info(f"Initialized Gemini model: {model_name}")
        self.model = GenerativeModel(model_name)
    
    def _generate_prompt(self, schema: ExtractionSchema) -> str:
        """Generate a prompt for the Gemini model based on the extraction schema"""
        # Create a list of fields with nested structure
        field_descriptions = []
        
        # Process all fields
        for field in schema.fields:
            is_parent = field.field_type == "object"
            has_parent = field.parent_field is not None
            
            # Skip child fields as they'll be handled when processing parents
            if has_parent:
                continue
                
            if is_parent:
                # This is a parent object field
                child_fields = schema.get_child_fields(field.name)
                child_desc = ""
                
                if child_fields:
                    child_desc = " Contains fields: " + ", ".join([
                        f"{child.name} ({child.description}, Type: {child.field_type})"
                        for child in child_fields
                    ])
                
                field_descriptions.append(f"- {field.name}: {field.description}{child_desc} (Type: {field.field_type})")
            else:
                # Regular field
                field_descriptions.append(f"- {field.name}: {field.description} (Type: {field.field_type})")
        
        fields_text = "\n".join(field_descriptions)
        
        prompt = f"""
        Extract the following information from the invoice or document:
        
        {fields_text}
        
        Return the extracted data as a JSON object with the field names as keys.
        If a field is not found in the document, set its value to null.
        For fields of type 'list', return an array of objects.
        For fields of type 'object', return a nested object with the child fields.
        
        Important: Return ONLY valid JSON in this exact format:
        ```json
        {{
          "field1": "value1",
          "field2": "value2",
          "object_field": {{
            "child_field1": "value3"
          }},
          "list_field": [
            {{ "item": "item1", "value": "10.00" }},
            {{ "item": "item2", "value": "20.00" }}
          ]
        }}
        ```
        
        Do not include any explanations, notes, or additional text outside the JSON.
        """
        return prompt
    
    async def process_file(self, file_path: str) -> tuple:
        """Process a file (image or PDF) using the Gemini model"""
        try:
            logger.info(f"Processing file: {file_path}")
            
            # Read the file
            with open(file_path, "rb") as f:
                file_content = f.read()
            
            logger.info(f"Read file: {len(file_content)} bytes")
            
            # Determine MIME type based on file extension
            if file_path.lower().endswith('.pdf'):
                mime_type = "application/pdf"
            else:
                mime_type = "image/jpeg"  # Default to image/jpeg for most images
            
            logger.info(f"Using mime type: {mime_type}")
            
            return file_content, mime_type
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {str(e)}")
            return None, None
    
    async def process_document(self, file_paths: list, schema: ExtractionSchema) -> dict:
        """Process document(s) using the Gemini model"""
        try:
            prompt = self._generate_prompt(schema)
            content_parts = [prompt]
            
            # Process each file
            for file_path in file_paths:
                file_content, mime_type = await self.process_file(file_path)
                if file_content:
                    content_parts.append(Part.from_data(file_content, mime_type))
            
            # Generate content using Gemini
            logger.info("Sending request to Vertex AI")
            response = self.model.generate_content(
                content_parts,
                generation_config=self.generation_config,
                stream=False
            )
            
            # Extract JSON from response
            text = response.text
            
            # Handle code blocks in response
            if "```json" in text and "```" in text:
                # Extract JSON from code block
                json_text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                # Extract from generic code block
                json_text = text.split("```")[1].split("```")[0].strip()
            else:
                # Use the whole text
                json_text = text
            
            try:
                # Parse the JSON
                result = json.loads(json_text)
                return result
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing JSON response: {str(e)}")
                logger.error(f"Response text: {text}")
                
                # Try to clean up the response and parse again
                json_text = text.replace("```json", "").replace("```", "").strip()
                try:
                    result = json.loads(json_text)
                    return result
                except json.JSONDecodeError:
                    # Return the text so we have something to work with
                    return {"error": "Failed to parse JSON", "raw_text": text}
        except Exception as e:
            logger.error(f"Error processing file with Gemini: {str(e)}")
            return {"error": str(e)} 