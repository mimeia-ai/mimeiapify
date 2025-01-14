import requests
import time
import json
import pandas as pd
import base64
from typing import Union

def get_schema(base_id, airtable_token):
    """
    Fetch the schema of an Airtable base.
    
    Args:
        base_id (str): The ID of the Airtable base.
        airtable_token (str): API token to authenticate the request.
    
    Returns:
        dict: A dictionary representing the schema of the Airtable base.
    """
    url = f'https://api.airtable.com/v0/meta/bases/{base_id}/tables'
    headers = {'Authorization': f'Bearer {airtable_token}'}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Failed to retrieve schema. Status code: {response.status_code}")
        return None

def extract_table_ids(schema):
    """
    Extract table IDs from an Airtable schema.
    
    Args:
        schema (dict): The schema dictionary from Airtable API.
    
    Returns:
        dict: A dictionary mapping table names to table IDs.
    """
    tables = schema.get('tables', [])
    table_ids = {}
    for table in tables:
        table_id = table['id']
        table_name = table['name']
        table_ids[table_name] = table_id
    return table_ids

# Function to create fields in a given table one at a time
def create_airtable_fields(base_id, table_id, api_key, fields):
    """
    Create fields in an Airtable table one at a time.

    Args:
        base_id (str): The ID of the Airtable base where the table is located.
        table_id (str): The ID of the table where the fields will be created.
        api_key (str): Airtable API key to authenticate the request.
        fields (list): A list of dictionaries where each dictionary represents a field to be created.
            Each field dictionary must include:
                - 'name' (str): The name of the field.
                - 'description' (str, optional): A description of the field.
                - 'type' (str): The field type, which must be one of the following valid field types:
                    - "singleLineText"
                    - "multilineText" (Long Text)
                    - "richText"
                    - "checkbox"
                    - "number"
                    - "percent"
                    - "currency"
                    - "rating"
                    - "date"
                    - "dateTime"
                    - "duration"
                    - "phoneNumber"
                    - "email"
                    - "url"
                    - "singleSelect"
                    - "multipleSelects"
                    - "singleCollaborator"
                    - "multipleCollaborators"
                    - "multipleAttachments"
                    - "multipleRecordLinks"
                    - "barcode"
                - 'options' (dict, optional): Field-specific options. See below for options per field type.

    Field Type Options:
        - **Checkbox** ("checkbox"):
            - `color` (str): One of
                "greenBright", "tealBright", "cyanBright", "blueBright", "purpleBright",
                "pinkBright", "redBright", "orangeBright", "yellowBright", "grayBright".
            - `icon` (str): One of "check", "xCheckbox", "star", "heart", "thumbsUp", "flag", "dot".

        - **Number** ("number") and **Percent** ("percent"):
            - `precision` (int): Number of decimal places (0 to 8 inclusive).

        - **Currency** ("currency"):
            - `precision` (int): Number of decimal places (0 to 7 inclusive).
            - `symbol` (str): Currency symbol (e.g., "$", "€", "¥").

        - **Rating** ("rating"):
            - `max` (int): Maximum rating value (1 to 10 inclusive).
            - `icon` (str): One of "star", "heart", "thumbsUp", "flag", "dot".
            - `color` (str): One of
                "yellowBright", "orangeBright", "redBright", "pinkBright", "purpleBright",
                "blueBright", "cyanBright", "tealBright", "greenBright", "grayBright".

        - **Date** ("date"):
            - `dateFormat` (dict):
                - `name` (str): One of "local", "friendly", "us", "european", "iso".
                - `format` (str, optional): Corresponding date format string.

        - **Date and Time** ("dateTime"):
            - `timeZone` (str): Timezone identifier (e.g., "UTC", "America/Los_Angeles").
            - `dateFormat` (dict):
                - `name` (str): One of "local", "friendly", "us", "european", "iso".
                - `format` (str, optional): Corresponding date format string.
            - `timeFormat` (dict):
                - `name` (str): One of "12hour", "24hour".
                - `format` (str, optional): Corresponding time format string.

        - **Duration** ("duration"):
            - `durationFormat` (str): One of
                "h:mm", "h:mm:ss", "h:mm:ss.S", "h:mm:ss.SS", "h:mm:ss.SSS".

        - **Single Select** ("singleSelect") and **Multiple Select** ("multipleSelects"):
            - `choices` (list of dicts): Each dict represents a choice with:
                - `name` (str): Name of the choice.
                - `color` (str, optional): One of the following colors:
                    "blueLight2", "cyanLight2", "tealLight2", "greenLight2", "yellowLight2",
                    "orangeLight2", "redLight2", "pinkLight2", "purpleLight2", "grayLight2",
                    "blueLight1", "cyanLight1", "tealLight1", "greenLight1", "yellowLight1",
                    "orangeLight1", "redLight1", "pinkLight1", "purpleLight1", "grayLight1",
                    "blueBright", "cyanBright", "tealBright", "greenBright", "yellowBright",
                    "orangeBright", "redBright", "pinkBright", "purpleBright", "grayBright",
                    "blueDark1", "cyanDark1", "tealDark1", "greenDark1", "yellowDark1",
                    "orangeDark1", "redDark1", "pinkDark1", "purpleDark1", "grayDark1".

        - **Link to Another Record** ("multipleRecordLinks"):
            - `linkedTableId` (str): The ID of the table to link to.
            - `viewIdForRecordSelection` (str, optional): ID of the view in the linked table.

        - **Attachment** ("multipleAttachments"):
            - `isReversed` (bool): Whether attachments are displayed in reverse order.

    Returns:
        None
        Prints the result of each field creation attempt, either success or failure.

    Notes:
        - Only certain field types can be created via the Airtable API. See the list above for supported field types and their options.
        - Field types like "formula", "rollup", "count", "lookup", "createdTime", "lastModifiedTime", and "autoNumber" are read-only and cannot be created or modified via the API.
        - For more details on the Airtable field model and field options, refer to the official Airtable documentation:
          https://airtable.com/developers/web/api/field-model
    """
    # API endpoint
    url = f"https://api.airtable.com/v0/meta/bases/{base_id}/tables/{table_id}/fields"
    
    # Headers for the POST request
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Iterate over each field and send a POST request to create the field
    for field in fields:
        # Make the POST request for each field
        response = requests.post(url, headers=headers, data=json.dumps(field))

        # Check if the field creation was successful
        if response.status_code == 200:
            print(f"Field '{field['name']}' created successfully!")
            print(response.json())  # Print the created field schema
        else:
            print(f"Failed to create field '{field['name']}'. Status code: {response.status_code}")
            print(response.text)

        # Add a small delay to avoid hitting API rate limits
        time.sleep(1)

def fetch_airtable_records(base_id, table_id, airt_token, json_format=False):
    """
    Fetch all records from a specified Airtable table.

    Args:
        base_id (str): The ID of the Airtable base.
        table_id (str): The ID of the table to fetch records from.
        airt_token (str): Airtable API token for authentication.
        json_format (bool, optional): If True, returns data as JSON object. If False, returns pandas DataFrame.
                                    Defaults to False.

    Returns:
        Union[pandas.DataFrame, dict]: 
            - If json_format=False: DataFrame where each row is a record from the Airtable table
            - If json_format=True: Dictionary containing the raw API response with records
    """
    
    # Initialize variables
    url = f"https://api.airtable.com/v0/{base_id}/{table_id}"
    headers = {
        "Authorization": f"Bearer {airt_token}"
    }
    
    records = []
    offset = None

    # Loop to fetch all pages
    while True:
        # Set up parameters including offset if present
        params = {}
        if offset:
            params['offset'] = offset

        # Make the request to the Airtable API
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()  # Raise an exception for any bad responses

        # Get the JSON data from the response
        data = response.json()

        # Process each record and include the record ID
        for record in data['records']:
            record_data = record['fields'].copy()  # Get the fields of the record
            record_data['record_id'] = record['id']  # Add the record_id to the fields
            records.append(record_data)  # Append to the list

        # Check if there is more data (pagination)
        if 'offset' in data:
            offset = data['offset']
        else:
            break

    # After collecting all records
    if json_format:
        return {"records": records}
    else:
        return pd.DataFrame(records)

def fetch_filtered_airtable_records(base_id, table_id, airt_token, filter_formula, json_format=False):
    """
    Fetch filtered records from a specified Airtable table using a formula.

    Args:
        base_id (str): The ID of the Airtable base.
        table_id (str): The ID of the table to fetch records from.
        airt_token (str): Airtable API token for authentication.
        filter_formula (str): Airtable formula to filter records.
            Examples:
            - "AND({Name}='John', {Age}>30)"
            - "OR({Status}='Active', {Status}='Pending')"
            - "FIND('urgent', LOWER({Tags}))"
        json_format (bool, optional): If True, returns data as JSON object. If False, returns pandas DataFrame.
                                    Defaults to False.

    Returns:
        Union[pandas.DataFrame, dict]: 
            - If json_format=False: DataFrame containing the filtered records
            - If json_format=True: Dictionary containing the raw API response with filtered records
    """
    url = f"https://api.airtable.com/v0/{base_id}/{table_id}"
    headers = {
        "Authorization": f"Bearer {airt_token}"
    }
    
    records = []
    offset = None

    # Loop to fetch all pages
    while True:
        # Set up parameters including filter and offset if present
        params = {
            'filterByFormula': filter_formula
        }
        if offset:
            params['offset'] = offset

        # Make the request to the Airtable API
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()  # Raise an exception for bad responses

        data = response.json()

        # Process each record and include the record ID
        for record in data['records']:
            record_data = record['fields'].copy()
            record_data['record_id'] = record['id']
            records.append(record_data)

        # Check if there is more data (pagination)
        if 'offset' in data:
            offset = data['offset']
        else:
            break

    # After collecting all records
    if json_format:
        return {"records": records}
    else:
        return pd.DataFrame(records)

def create_airtable_records(base_id, table_id, api_key, records, typecast=False, return_fields_by_field_id=False):
    """
    Create one or multiple records in an Airtable table.

    Args:
        base_id (str): The ID of the Airtable base.
        table_id (str): The ID of the table where records will be created.
        api_key (str): Airtable API key to authenticate the request.
        records (list of dict or dict): 
            - To create multiple records, provide a list of dictionaries where each dictionary represents a record.
              Each record dictionary must have a "fields" key with a dictionary of field names/IDs and their corresponding values.
            - To create a single record, provide a single dictionary with a "fields" key.
        typecast (bool, optional): 
            If True, Airtable will perform best-effort automatic data conversion from string values.
            Defaults to False.
        return_fields_by_field_id (bool, optional): 
            If True, the response will return fields keyed by field ID.
            Defaults to False.

    Returns:
        list: A list of dictionaries representing the created records, each containing 'id', 'createdTime', and 'fields'.
              Returns None if the creation fails.

    Notes:
        - You can create up to 10 records per request.
        - If more than 10 records are provided, the function will batch the requests accordingly.
        - Field types must be writable as per Airtable's API specifications.
        - Example of a single record:
            {
                "fields": {
                    "Name": "John Doe",
                    "Email": "john.doe@example.com",
                    "Age": 30
                }
            }
        - Example of multiple records:
            [
                {
                    "fields": {
                        "Name": "John Doe",
                        "Email": "john.doe@example.com",
                        "Age": 30
                    }
                },
                {
                    "fields": {
                        "Name": "Jane Smith",
                        "Email": "jane.smith@example.com",
                        "Age": 25
                    }
                }
            ]
    """
    url = f"https://api.airtable.com/v0/{base_id}/{table_id}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Ensure records is a list
    if isinstance(records, dict):
        records = [records]

    created_records = []

    # Airtable allows up to 10 records per request
    for i in range(0, len(records), 10):
        batch = records[i:i+10]
        payload = {
            "records": batch,
            "typecast": typecast,
            "returnFieldsByFieldId": return_fields_by_field_id
        }
        response = requests.post(url, headers=headers, data=json.dumps(payload))

        if response.status_code == 200:
            batch_response = response.json().get('records', [])
            created_records.extend(batch_response)
            print(f"Batch {i//10 + 1}: Successfully created {len(batch)} records.")
        else:
            print(f"Batch {i//10 + 1}: Failed to create records. Status code: {response.status_code}")
            print(response.text)

        # Delay to respect rate limits
        time.sleep(1)

    return created_records if created_records else None


def update_single_airtable_record(base_id, table_id, record_id, api_key, fields, typecast=False, return_fields_by_field_id=False):
    """
    Update a single record in an Airtable table.

    Args:
        base_id (str): The ID of the Airtable base.
        table_id (str): The ID of the table containing the record.
        record_id (str): The ID of the record to update.
        api_key (str): Airtable API key to authenticate the request.
        fields (dict): A dictionary of fields to update with their new values.
            Example:
                {
                    "Name": "John Doe Updated",
                    "Email": "john.doe.updated@example.com"
                }
        typecast (bool, optional): 
            If True, Airtable will perform best-effort automatic data conversion from string values.
            Defaults to False.
        return_fields_by_field_id (bool, optional): 
            If True, the response will return fields keyed by field ID.
            Defaults to False.

    Returns:
        dict: A dictionary representing the updated record, containing 'id', 'createdTime', and 'fields'.
              Returns None if the update fails.

    Notes:
        - Only the specified fields will be updated; other fields remain unchanged.
        - Field types must be writable as per Airtable's API specifications.
    """
    url = f"https://api.airtable.com/v0/{base_id}/{table_id}/{record_id}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "fields": fields,
        "typecast": typecast,
        "returnFieldsByFieldId": return_fields_by_field_id
    }

    response = requests.patch(url, headers=headers, data=json.dumps(payload))

    if response.status_code == 200:
        updated_record = response.json()
        print(f"Record '{record_id}' updated successfully!")
        return updated_record
    else:
        print(f"Failed to update record '{record_id}'. Status code: {response.status_code}")
        print(response.text)
        return None


def update_multiple_airtable_records(base_id, table_id, api_key, records, typecast=False, return_fields_by_field_id=False, perform_upsert=False, fields_to_merge_on=None):
    """
    Update multiple records in an Airtable table or perform upserts.

    Args:
        base_id (str): The ID of the Airtable base.
        table_id (str): The ID of the table containing the records.
        api_key (str): Airtable API key to authenticate the request.
        records (list of dict): A list of dictionaries representing the records to update.
            Each dictionary must have:
                - 'id' (str, optional): The ID of the record to update. Required unless performing an upsert.
                - 'fields' (dict): A dictionary of fields to update with their new values.
            Example:
                [
                    {
                        "id": "rec1234567890",
                        "fields": {
                            "Name": "John Doe Updated",
                            "Email": "john.doe.updated@example.com"
                        }
                    },
                    {
                        "id": "rec0987654321",
                        "fields": {
                            "Name": "Jane Smith Updated",
                            "Email": "jane.smith.updated@example.com"
                        }
                    }
                ]
        typecast (bool, optional): 
            If True, Airtable will perform best-effort automatic data conversion from string values.
            Defaults to False.
        return_fields_by_field_id (bool, optional): 
            If True, the response will return fields keyed by field ID.
            Defaults to False.
        perform_upsert (bool, optional): 
            If True, enables upsert behavior. Records without an 'id' will be created or matched based on 'fieldsToMergeOn'.
            Defaults to False.
        fields_to_merge_on (list of str, optional): 
            An array of field names or IDs to use as external IDs for upserting. Required if perform_upsert is True.
            Example: ["Email", "Name"]

    Returns:
        dict: A dictionary containing lists of 'records', 'createdRecords', and 'updatedRecords'.
              Returns None if the update fails.

    Notes:
        - You can update up to 10 records per request.
        - If more than 10 records are provided, the function will batch the requests accordingly.
        - When performing upserts, ensure that 'fields_to_merge_on' uniquely identify records.
    """
    url = f"https://api.airtable.com/v0/{base_id}/{table_id}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Ensure records is a list
    if isinstance(records, dict):
        records = [records]

    all_updated_records = {
        "records": [],
        "createdRecords": [],
        "updatedRecords": []
    }

    # Airtable allows up to 10 records per request
    for i in range(0, len(records), 10):
        batch = records[i:i+10]
        payload = {
            "records": batch,
            "typecast": typecast,
            "returnFieldsByFieldId": return_fields_by_field_id
        }

        if perform_upsert:
            if not fields_to_merge_on:
                print("Error: 'fields_to_merge_on' must be provided when perform_upsert is True.")
                return None
            payload["performUpsert"] = {
                "fieldsToMergeOn": fields_to_merge_on
            }

        response = requests.patch(url, headers=headers, data=json.dumps(payload))

        if response.status_code == 200:
            batch_response = response.json()
            all_updated_records["records"].extend(batch_response.get("records", []))
            if perform_upsert:
                all_updated_records["createdRecords"].extend(batch_response.get("createdRecords", []))
                all_updated_records["updatedRecords"].extend(batch_response.get("updatedRecords", []))
            print(f"Batch {i//10 + 1}: Successfully updated {len(batch)} records.")
        else:
            print(f"Batch {i//10 + 1}: Failed to update records. Status code: {response.status_code}")
            print(response.text)

        # Delay to respect rate limits
        time.sleep(1)

    return all_updated_records if all_updated_records["records"] else None


def delete_single_airtable_record(base_id, table_id, record_id, api_key):
    """
    Delete a single record from an Airtable table.

    Args:
        base_id (str): The ID of the Airtable base.
        table_id (str): The ID of the table containing the record.
        record_id (str): The ID of the record to delete.
        api_key (str): Airtable API key to authenticate the request.

    Returns:
        bool: True if the record was deleted successfully, False otherwise.

    Notes:
        - Ensure that the API key has the necessary permissions to delete records.
    """
    url = f"https://api.airtable.com/v0/{base_id}/{table_id}/{record_id}"
    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    response = requests.delete(url, headers=headers)

    if response.status_code == 200:
        print(f"Record '{record_id}' deleted successfully!")
        return True
    else:
        print(f"Failed to delete record '{record_id}'. Status code: {response.status_code}")
        print(response.text)
        return False


def delete_multiple_airtable_records(base_id, table_id, record_ids, api_key):
    """
    Delete multiple records from an Airtable table.

    Args:
        base_id (str): The ID of the Airtable base.
        table_id (str): The ID of the table containing the records.
        record_ids (list of str): A list of record IDs to delete. Up to 10 record IDs can be provided per request.
        api_key (str): Airtable API key to authenticate the request.

    Returns:
        list: A list of dictionaries indicating the deletion status for each record.
              Example:
              [
                  {"deleted": True, "id": "rec1234567890"},
                  {"deleted": True, "id": "rec0987654321"}
              ]
              Returns None if the deletion fails.

    Notes:
        - You can delete up to 10 records per request.
        - If more than 10 records are provided, the function will batch the requests accordingly.
    """
    url = f"https://api.airtable.com/v0/{base_id}/{table_id}"
    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    # Ensure record_ids is a list
    if isinstance(record_ids, str):
        record_ids = [record_ids]

    all_deletions = []

    # Airtable allows up to 10 records per request
    for i in range(0, len(record_ids), 10):
        batch = record_ids[i:i+10]
        params = {
            "records[]": batch
        }

        response = requests.delete(url, headers=headers, params=params)

        if response.status_code == 200:
            batch_response = response.json().get("records", [])
            all_deletions.extend(batch_response)
            print(f"Batch {i//10 + 1}: Successfully deleted {len(batch)} records.")
        else:
            print(f"Batch {i//10 + 1}: Failed to delete records. Status code: {response.status_code}")
            print(response.text)

        # Delay to respect rate limits
        time.sleep(1)

    return all_deletions if all_deletions else None


def upload_airtable_attachment(base_id, record_id, attachment_field, api_key, content_type, file_bytes, filename):
    """
    Upload an attachment to a specific attachment field in an Airtable record.

    Args:
        base_id (str): The ID of the Airtable base.
        record_id (str): The ID of the record to upload the attachment to.
        attachment_field (str): The ID or name of the attachment field.
        api_key (str): Airtable API key to authenticate the request.
        content_type (str): The MIME type of the file, e.g., "image/jpeg".
        file_bytes (bytes): The binary content of the file to upload.
        filename (str): The name of the file, e.g., "photo.jpg".

    Returns:
        dict: A dictionary containing the 'id', 'createdTime', and updated 'fields' with the attachment.
              Returns None if the upload fails.

    Notes:
        - The file size must not exceed 5 MB.
        - Ensure that the attachment field is configured to accept attachments.
        - The 'file_bytes' should be base64 encoded before being passed to the function.
    """
    url = f"https://content.airtable.com/v0/{base_id}/{record_id}/{attachment_field}/uploadAttachment"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Encode the file bytes to base64
    encoded_file = base64.b64encode(file_bytes).decode('utf-8')

    payload = {
        "contentType": content_type,
        "file": encoded_file,
        "filename": filename
    }

    response = requests.post(url, headers=headers, data=json.dumps(payload))

    if response.status_code == 200:
        attachment_response = response.json()
        print(f"Attachment '{filename}' uploaded successfully to record '{record_id}'!")
        return attachment_response
    else:
        print(f"Failed to upload attachment '{filename}' to record '{record_id}'. Status code: {response.status_code}")
        print(response.text)
        return None


def update_airtable_field(base_id, table_id, column_id, api_key, name=None, description=None):
    """
    Update the name and/or description of a field in an Airtable table.

    Args:
        base_id (str): The ID of the Airtable base.
        table_id (str): The ID of the table containing the field.
        column_id (str): The ID of the column (field) to update.
        api_key (str): Airtable API key to authenticate the request.
        name (str, optional): The new name for the field.
        description (str, optional): The new description for the field. Must be no longer than 20,000 characters.

    Returns:
        dict: A dictionary representing the updated field, containing 'id', 'name', 'description', and 'type'.
              Returns None if the update fails.

    Notes:
        - At least one of 'name' or 'description' must be provided.
        - Field types cannot be changed via this function; only the name and description can be updated.
    """
    if not name and not description:
        print("Error: At least one of 'name' or 'description' must be provided.")
        return None

    url = f"https://api.airtable.com/v0/meta/bases/{base_id}/tables/{table_id}/fields/{column_id}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {}
    if name:
        payload["name"] = name
    if description:
        payload["description"] = description

    response = requests.patch(url, headers=headers, data=json.dumps(payload))

    if response.status_code == 200:
        updated_field = response.json()
        print(f"Field '{column_id}' updated successfully!")
        return updated_field
    else:
        print(f"Failed to update field '{column_id}'. Status code: {response.status_code}")
        print(response.text)
        return None