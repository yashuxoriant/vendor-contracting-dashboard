"""
Analyze Client BOM Files
Parse Excel BOMs to understand structure, patterns, and content
"""

import pandas as pd
import json
from pathlib import Path

def analyze_excel_bom(file_path):
    """
    Comprehensive analysis of a BOM Excel file
    """
    print(f"\n{'='*80}")
    print(f"ANALYZING: {Path(file_path).name}")
    print(f"{'='*80}\n")
    
    try:
        # Read Excel file - get all sheet names first
        xl_file = pd.ExcelFile(file_path)
        print(f"📊 Sheet Names: {xl_file.sheet_names}\n")
        
        analysis = {
            "file": Path(file_path).name,
            "sheets": [],
            "patterns": {}
        }
        
        # Analyze each sheet
        for sheet_name in xl_file.sheet_names:
            print(f"\n{'─'*80}")
            print(f"SHEET: {sheet_name}")
            print(f"{'─'*80}")
            
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            
            sheet_info = {
                "name": sheet_name,
                "rows": len(df),
                "columns": list(df.columns),
                "sample_data": []
            }
            
            print(f"\n📏 Dimensions: {len(df)} rows × {len(df.columns)} columns")
            print(f"\n📋 Column Names:")
            for i, col in enumerate(df.columns, 1):
                print(f"  {i:2d}. {col}")
            
            # Show first few rows
            print(f"\n🔍 First 5 Rows Preview:")
            print(df.head().to_string())
            
            # Data types
            print(f"\n📊 Data Types:")
            print(df.dtypes.to_string())
            
            # Check for key BOM fields
            print(f"\n🔑 Key BOM Fields Detected:")
            key_fields = {
                'description': ['description', 'item', 'name', 'product', 'component'],
                'sku': ['sku', 'part', 'model', 'part number', 'item number'],
                'quantity': ['qty', 'quantity', 'count', 'units'],
                'price': ['price', 'cost', 'unit price', 'amount', 'rate'],
                'vendor': ['vendor', 'manufacturer', 'supplier', 'mfr'],
                'category': ['category', 'type', 'class', 'group']
            }
            
            detected_fields = {}
            for field_type, possible_names in key_fields.items():
                matches = [col for col in df.columns 
                          if any(name.lower() in col.lower() for name in possible_names)]
                if matches:
                    detected_fields[field_type] = matches
                    print(f"  ✅ {field_type.upper()}: {matches}")
            
            sheet_info["detected_fields"] = detected_fields
            
            # Statistics
            print(f"\n📈 Statistics:")
            numeric_cols = df.select_dtypes(include=['number']).columns
            if len(numeric_cols) > 0:
                print(df[numeric_cols].describe().to_string())
            
            # Sample 3 complete rows
            if len(df) > 0:
                sample_indices = [0, len(df)//2, -1] if len(df) > 2 else [0]
                for idx in sample_indices:
                    row_dict = df.iloc[idx].to_dict()
                    sheet_info["sample_data"].append({k: str(v) for k, v in row_dict.items()})
            
            analysis["sheets"].append(sheet_info)
            
        # Save analysis to JSON
        output_file = Path(file_path).stem + "_analysis.json"
        with open(output_file, 'w') as f:
            json.dump(analysis, f, indent=2)
        
        print(f"\n\n✅ Analysis saved to: {output_file}")
        
    except Exception as e:
        print(f"❌ Error analyzing file: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Analyze both client BOM files
    bom_files = [
        "Colo_BOM_Rev5.xlsx",
        "Data Center BoM - Honeywell (1).xlsx"
    ]
    
    for bom_file in bom_files:
        if Path(bom_file).exists():
            analyze_excel_bom(bom_file)
        else:
            print(f"❌ File not found: {bom_file}")
