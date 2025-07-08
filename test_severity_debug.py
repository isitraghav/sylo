#!/usr/bin/env python3
"""
Test script to debug severity data processing
This script helps identify what severity values exist in your data
"""

# Sample anomaly data to test with (replace this with your actual data structure)
sample_anomalies = [
    {
        'properties': {
            'Block': '1',
            'Severity': 'High',
            'Anomaly': 'Cell Hotspot'
        }
    },
    {
        'properties': {
            'Block': '1', 
            'Severity': 'Medium',
            'Anomaly': 'Multi Cell'
        }
    },
    {
        'properties': {
            'Block': '2',
            'Severity': 'Low', 
            'Anomaly': 'Shading'
        }
    },
    {
        'properties': {
            'Block': '2',
            'Severity': 'High',
            'Anomaly': 'Bypass Diode'
        }
    }
]

def test_severity_processing(anomalies):
    """Test the severity data processing logic"""
    severity_blocks_data = {}
    severity_values_found = set()
    
    # Process anomalies to group by severity and blocks
    for anomaly in anomalies:
        properties = anomaly['properties']
        block_value = properties.get('Block', 'Unknown')
        severity_value = properties.get('Severity', 'Unknown')
        
        # Debug: collect all severity values found
        if severity_value != 'Unknown':
            severity_values_found.add(severity_value)
        
        print(f"🔍 Processing anomaly - Block: {block_value}, Severity: {severity_value}")
        
        if block_value != 'Unknown' and severity_value != 'Unknown':
            if block_value not in severity_blocks_data:
                severity_blocks_data[block_value] = {}
            
            # Normalize severity value to standard format
            normalized_severity = severity_value.strip().title()
            
            if normalized_severity in severity_blocks_data[block_value]:
                severity_blocks_data[block_value][normalized_severity] += 1
            else:
                severity_blocks_data[block_value][normalized_severity] = 1
    
    print(f"📊 Found severity values: {severity_values_found}")
    print(f"📊 Severity blocks data: {severity_blocks_data}")
    
    # Prepare chart data
    if severity_blocks_data:
        sorted_severity_blocks = sorted(severity_blocks_data.keys())
        labels = [f'Block {block}' for block in sorted_severity_blocks]
        
        # Define severity levels and their colors
        severity_levels = {
            'High': '#DC2626',
            'Medium': '#F59E0B', 
            'Low': '#10B981',
            'Critical': '#DC2626',
            'Moderate': '#F59E0B',
            'Minor': '#10B981',
            'Severe': '#DC2626'
        }
        
        # Get all unique severity levels from the data
        all_severities_in_data = set()
        for block_data in severity_blocks_data.values():
            all_severities_in_data.update(block_data.keys())
        
        print(f"📊 All severities in data: {all_severities_in_data}")
        
        # Create datasets for each severity level found in data
        datasets = []
        for severity_level in all_severities_in_data:
            # Use predefined color or default
            color = severity_levels.get(severity_level, '#888888')
            
            data_values = []
            for block in sorted_severity_blocks:
                count = severity_blocks_data[block].get(severity_level, 0)
                data_values.append(count)
            
            datasets.append({
                'label': f'{severity_level} Severity',
                'data': data_values,
                'backgroundColor': color,
                'barThickness': 30
            })
        
        severity_chart_data = {
            'labels': labels,
            'datasets': datasets
        }
        
        print(f"📊 Final chart data: {severity_chart_data}")
        return severity_chart_data
    else:
        print("⚠️ No severity blocks data found")
        return None

if __name__ == "__main__":
    print("🧪 Testing severity data processing...")
    print("=" * 50)
    
    result = test_severity_processing(sample_anomalies)
    
    if result:
        print("\n✅ SUCCESS: Severity chart data generated")
        print(f"Labels: {result['labels']}")
        print(f"Datasets: {len(result['datasets'])} severity levels")
        for dataset in result['datasets']:
            print(f"  - {dataset['label']}: {dataset['data']}")
    else:
        print("\n❌ FAILED: No severity data processed")
    
    print("\n" + "=" * 50)
    print("To debug your actual data:")
    print("1. Check what values are in the 'Severity' field of your anomaly data")
    print("2. Ensure the values match 'High', 'Medium', 'Low' (case-insensitive)")
    print("3. Check the server logs when accessing the overview page")
