import uuid
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field as PydanticField
from datetime import datetime
from enum import Enum


class FieldType(str, Enum):
    """Field types for schema fields"""
    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    DATE = "date"
    LIST = "list"
    OBJECT = "object"


class Field(BaseModel):
    """Schema field definition"""
    name: str
    description: str = ""
    field_type: str  # string, number, date, list, object
    required: bool = False
    constraints: Dict[str, Any] = {}
    parent_field: Optional[str] = None  # New field to track parent-child relationships
    child_fields: Optional[List[Dict]] = []  # Store child fields if this is a parent object

    def dict(self):
        """Return a dictionary representation of the field"""
        return {
            "name": self.name,
            "description": self.description,
            "field_type": self.field_type,
            "required": self.required,
            "constraints": self.constraints,
            "parent_field": self.parent_field,
            "child_fields": self.child_fields
        }


class DocumentMetadata(BaseModel):
    """Document metadata"""
    source: Optional[str] = None
    page_count: Optional[int] = None
    file_type: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None


class ExtractionSchema(BaseModel):
    """Schema for extraction"""
    id: int = 1
    name: str = "Untitled Schema"
    description: str = ""
    fields: List[Field] = []
    metadata: Optional[DocumentMetadata] = None

    def get_field_names(self) -> List[str]:
        """Get all field names in the schema"""
        return [field.name for field in self.fields]
    
    def get_field_by_name(self, name: str) -> Optional[Field]:
        """Get field by name"""
        for field in self.fields:
            if field.name == name:
                return field
        return None
    
    def get_parent_fields(self) -> List[Field]:
        """Get all parent fields (objects that can contain child fields)"""
        return [field for field in self.fields if field.field_type == "object"]
    
    def get_child_fields(self, parent_name: str) -> List[Field]:
        """Get all child fields for a given parent"""
        return [field for field in self.fields if field.parent_field == parent_name]
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExtractionSchema':
        """Create an ExtractionSchema instance from a dictionary"""
        fields = []
        if "fields" in data and data["fields"]:
            # Convert raw field dictionaries to Field objects
            for field_data in data["fields"]:
                if isinstance(field_data, dict):
                    fields.append(Field(**field_data))
                elif isinstance(field_data, Field):
                    fields.append(field_data)
        
        return cls(
            id=data.get("id"),
            name=data.get("name", ""),
            description=data.get("description", ""),
            fields=fields
        )

    def __init__(self, **data):
        if "fields" not in data:
            data["fields"] = [
                Field(
                    name="invoice_number",
                    description="The invoice identifier",
                    field_type="string"
                ),
                Field(
                    name="invoice_date",
                    description="Date the invoice was issued",
                    field_type="date"
                ),
                Field(
                    name="total_amount",
                    description="Total amount due",
                    field_type="number"
                )
            ]
        
        if "name" not in data:
            data["name"] = "Invoice"
        if "description" not in data:
            data["description"] = "Default schema for extracting common invoice fields"
        if "id" not in data:
            data["id"] = 1
            
        super().__init__(**data)

    def add_field(self, field):
        # Implementation of add_field method
        pass


class SchemaResponse(BaseModel):
    """Schema response model"""
    id: int
    name: str
    description: str
    fields: List[Dict[str, Any]]
    created_at: str
    updated_at: str


class SchemasListResponse(BaseModel):
    """List of schemas response"""
    schemas: List[SchemaResponse]
    total: int


class ExtractionRecord(BaseModel):
    """Extraction record"""
    id: int
    schema_id: int
    file_name: str
    file_path: Optional[str] = None
    model_used: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    created_at: str


class ExtractionsListResponse(BaseModel):
    """List of extractions response"""
    extractions: List[ExtractionRecord]
    total: int


class InvoiceSchema(ExtractionSchema):
    """Default schema for invoice extraction"""
    
    def __init__(self, **data):
        if "fields" not in data:
            data["fields"] = [
                Field(name="invoice_number", description="The invoice identifier", field_type="string"),
                Field(name="invoice_date", description="Date the invoice was issued", field_type="date"),
                Field(name="due_date", description="Date payment is due", field_type="date"),
                Field(name="vendor_name", description="Name of the vendor/supplier", field_type="string"),
                Field(name="vendor_address", description="Address of the vendor", field_type="string"),
                Field(name="customer_name", description="Name of the customer", field_type="string"),
                Field(name="customer_address", description="Address of the customer", field_type="string"),
                Field(name="line_items", description="Products or services provided", field_type="list"),
                Field(name="subtotal", description="Sum of all line items before tax", field_type="number"),
                Field(name="tax_amount", description="Tax applied to the invoice", field_type="number"),
                Field(name="total_amount", description="Total amount due including tax", field_type="number"),
                Field(name="currency", description="Currency used in the invoice", field_type="string"),
                Field(name="payment_method", description="Method of payment", field_type="string"),
            ]
        if "name" not in data:
            data["name"] = "Invoice"
        if "description" not in data:
            data["description"] = "Default schema for extracting common invoice fields"
        if "id" not in data:
            data["id"] = 1
            
        super().__init__(**data) 