import aiohttp
import asyncio
import json
import pandas as pd
import base64
from typing import Union, Optional, List, Dict


class AirtableAsync:
    """
    An asynchronous class-based interface for interacting with an Airtable base 
    via the Airtable Web API. Instantiate with your base_id and api_key, then 
    call async methods to fetch, create, update, and delete records or fields.

    Example usage (with FastAPI):

        from fastapi import FastAPI
        from sncl.airtable_async import AirtableAsync

        app = FastAPI()

        @app.get("/schema")
        async def get_schema():
            airtable = AirtableAsync(base_id="YOUR_BASE_ID", api_key="YOUR_API_KEY")
            schema = await airtable.get_schema()
            return schema
    """

    def __init__(self, base_id: str, api_key: str):
        """
        Initialize the AirtableAsync client.

        Args:
            base_id (str): The ID of the Airtable base.
            api_key (str): Your Airtable API key (Bearer token).
        """
        self.base_id = base_id
        self.api_key = api_key

    async def get_schema(self) -> Optional[dict]:
        """
        Fetch the schema of an Airtable base.
        
        Returns:
            dict: A dictionary representing the schema of the Airtable base.
        """
        url = f"https://api.airtable.com/v0/meta/bases/{self.base_id}/tables"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    print(f"Failed to retrieve schema. Status code: {response.status}")
                    print(await response.text())
                    return None

    async def extract_table_ids(self, schema: dict) -> dict:
        """
        Extract table IDs from an Airtable schema dictionary.

        Args:
            schema (dict): The schema dictionary, typically returned by get_schema().

        Returns:
            dict: A dictionary mapping table names to table IDs.
        """
        tables = schema.get("tables", [])
        table_ids = {}
        for table in tables:
            table_id = table["id"]
            table_name = table["name"]
            table_ids[table_name] = table_id
        return table_ids

    async def create_fields(self, table_id: str, fields: List[dict]) -> None:
        """
        Create fields in a given Airtable table, one at a time.

        Args:
            table_id (str): The ID of the table where the fields will be created.
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
        url = f"https://api.airtable.com/v0/meta/bases/{self.base_id}/tables/{table_id}/fields"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            for field in fields:
                async with session.post(url, headers=headers, data=json.dumps(field)) as response:
                    if response.status == 200:
                        print(f"Field '{field['name']}' created successfully!")
                        resp_data = await response.json()
                        print(resp_data)
                    else:
                        print(f"Failed to create field '{field['name']}'. Status code: {response.status}")
                        print(await response.text())

    async def fetch_records(
        self,
        table_id: str,
        json_format: bool = False
    ) -> Union[pd.DataFrame, dict]:
        """
        Fetch all records from a specified table in this base.

        Args:
            table_id (str): The ID of the table to fetch records from.
            json_format (bool, optional): If True, returns data as a JSON-like dict; 
                                          else returns a pandas DataFrame.

        Returns:
            Union[pandas.DataFrame, dict]:
                - If json_format=False, a DataFrame of records.
                - If json_format=True, a dict with key "records" containing the raw data.
        """
        url = f"https://api.airtable.com/v0/{self.base_id}/{table_id}"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        records = []
        offset = None

        async with aiohttp.ClientSession() as session:
            while True:
                params = {}
                if offset:
                    params["offset"] = offset

                async with session.get(url, headers=headers, params=params) as response:
                    response.raise_for_status()
                    data = await response.json()

                    for record in data["records"]:
                        record_data = record["fields"].copy()
                        record_data["record_id"] = record["id"]
                        records.append(record_data)

                    offset = data.get("offset")
                    if not offset:
                        break

        if json_format:
            return {"records": records}
        else:
            return pd.DataFrame(records)

    async def fetch_filtered_records(
        self,
        table_id: str,
        filter_formula: str,
        json_format: bool = False
    ) -> Union[pd.DataFrame, dict]:
        """
        Fetch filtered records from a specified table using an Airtable formula.

        Args:
            table_id (str): The ID of the table to fetch records from.
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
        url = f"https://api.airtable.com/v0/{self.base_id}/{table_id}"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        records = []
        offset = None

        async with aiohttp.ClientSession() as session:
            while True:
                params = {"filterByFormula": filter_formula}
                if offset:
                    params["offset"] = offset

                async with session.get(url, headers=headers, params=params) as response:
                    response.raise_for_status()
                    data = await response.json()

                    for record in data["records"]:
                        record_data = record["fields"].copy()
                        record_data["record_id"] = record["id"]
                        records.append(record_data)

                    offset = data.get("offset")
                    if not offset:
                        break

        if json_format:
            return {"records": records}
        else:
            return pd.DataFrame(records)

    async def create_records(
        self,
        table_id: str,
        records: Union[List[dict], dict],
        typecast: bool = False,
        return_fields_by_field_id: bool = False
    ) -> Optional[List[dict]]:
        """
        Create one or multiple records in a table.

        Args:
            table_id (str): The ID of the table to insert records into.
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
        url = f"https://api.airtable.com/v0/{self.base_id}/{table_id}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        if isinstance(records, dict):
            records = [records]

        created_records: List[dict] = []

        async with aiohttp.ClientSession() as session:
            for i in range(0, len(records), 10):
                batch = records[i : i + 10]
                payload = {
                    "records": batch,
                    "typecast": typecast,
                    "returnFieldsByFieldId": return_fields_by_field_id
                }
                async with session.post(url, headers=headers, data=json.dumps(payload)) as response:
                    if response.status == 200:
                        batch_response = (await response.json()).get("records", [])
                        created_records.extend(batch_response)
                        print(f"Batch {i//10 + 1}: Successfully created {len(batch)} records.")
                    else:
                        print(f"Batch {i//10 + 1}: Failed to create records. Status code: {response.status}")
                        print(await response.text())

        return created_records if created_records else None

    async def update_single_record(
        self,
        table_id: str,
        record_id: str,
        fields: dict,
        typecast: bool = False,
        return_fields_by_field_id: bool = False
    ) -> Optional[dict]:
        """
        Update a single record in a table.

        Args:
        
            table_id (str): The ID of the table containing the record.
            record_id (str): The ID of the record to update.
        
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
        url = f"https://api.airtable.com/v0/{self.base_id}/{table_id}/{record_id}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "fields": fields,
            "typecast": typecast,
            "returnFieldsByFieldId": return_fields_by_field_id
        }

        async with aiohttp.ClientSession() as session:
            async with session.patch(url, headers=headers, data=json.dumps(payload)) as response:
                if response.status == 200:
                    updated_record = await response.json()
                    print(f"Record '{record_id}' updated successfully!")
                    return updated_record
                else:
                    print(f"Failed to update record '{record_id}'. Status code: {response.status}")
                    print(await response.text())
                    return None

    async def update_multiple_records(
        self,
        table_id: str,
        records: List[dict],
        typecast: bool = False,
        return_fields_by_field_id: bool = False,
        perform_upsert: bool = False,
        fields_to_merge_on: Optional[List[str]] = None
    ) -> Optional[dict]:
        """
        Update multiple records in a table or perform upserts.

        Args:
            table_id (str): The ID of the table containing the records.
        
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
        url = f"https://api.airtable.com/v0/{self.base_id}/{table_id}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        all_updated_records = {
            "records": [],
            "createdRecords": [],
            "updatedRecords": []
        }

        async with aiohttp.ClientSession() as session:
            for i in range(0, len(records), 10):
                batch = records[i : i + 10]
                payload: Dict[str, Union[List[dict], dict]] = {
                    "records": batch,
                    "typecast": typecast,
                    "returnFieldsByFieldId": return_fields_by_field_id
                }

                if perform_upsert:
                    if not fields_to_merge_on:
                        print("Error: 'fields_to_merge_on' must be provided when perform_upsert is True.")
                        return None
                    payload["performUpsert"] = {"fieldsToMergeOn": fields_to_merge_on}

                async with session.patch(url, headers=headers, data=json.dumps(payload)) as response:
                    if response.status == 200:
                        batch_response = await response.json()
                        all_updated_records["records"].extend(batch_response.get("records", []))

                        if perform_upsert:
                            all_updated_records["createdRecords"].extend(
                                batch_response.get("createdRecords", [])
                            )
                            all_updated_records["updatedRecords"].extend(
                                batch_response.get("updatedRecords", [])
                            )
                        print(f"Batch {i//10 + 1}: Successfully updated {len(batch)} records.")
                    else:
                        print(f"Batch {i//10 + 1}: Failed to update records. Status code: {response.status}")
                        print(await response.text())

        # Only return the data if we have something
        return all_updated_records if all_updated_records["records"] else None

    async def delete_single_record(self, table_id: str, record_id: str) -> bool:
        """
        Delete a single record from a table.

        Args:
            table_id (str): The ID of the table containing the record.
            record_id (str): The ID of the record to delete.

        Returns:
            bool: True if the record was deleted successfully, False otherwise.
        """
        url = f"https://api.airtable.com/v0/{self.base_id}/{table_id}/{record_id}"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        async with aiohttp.ClientSession() as session:
            async with session.delete(url, headers=headers) as response:
                if response.status == 200:
                    print(f"Record '{record_id}' deleted successfully!")
                    return True
                else:
                    print(f"Failed to delete record '{record_id}'. Status code: {response.status}")
                    print(await response.text())
                    return False

    async def delete_multiple_records(
        self,
        table_id: str,
        record_ids: Union[List[str], str]
    ) -> Optional[List[dict]]:
        """
        Delete multiple records from a table.

        Args:
            table_id (str): The ID of the table containing the records.
            record_ids (list of str or str): Up to 10 record IDs per request.

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
        url = f"https://api.airtable.com/v0/{self.base_id}/{table_id}"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        if isinstance(record_ids, str):
            record_ids = [record_ids]

        all_deletions: List[dict] = []

        async with aiohttp.ClientSession() as session:
            for i in range(0, len(record_ids), 10):
                batch = record_ids[i : i + 10]
                params = [("records[]", rid) for rid in batch]

                async with session.delete(url, headers=headers, params=params) as response:
                    if response.status == 200:
                        batch_response = (await response.json()).get("records", [])
                        all_deletions.extend(batch_response)
                        print(f"Batch {i//10 + 1}: Successfully deleted {len(batch)} records.")
                    else:
                        print(f"Batch {i//10 + 1}: Failed to delete records. Status code: {response.status}")
                        print(await response.text())

        return all_deletions if all_deletions else None

    async def upload_attachment(
        self,
        record_id: str,
        attachment_field: str,
        content_type: str,
        file_bytes: bytes,
        filename: str
    ) -> Optional[dict]:
        """
        Upload an attachment to a specific attachment field in a record.

        Args:
            record_id (str): The ID of the record to upload the attachment to.
            attachment_field (str): The field name or ID that holds the attachments.
            content_type (str): The MIME type of the file, e.g. "image/jpeg".
            file_bytes (bytes): The raw bytes of the file.
            filename (str): The filename, e.g. "photo.jpg".

        Returns:
            dict: A dictionary containing the 'id', 'createdTime', and updated 'fields' with the attachment.
                Returns None if the upload fails.

        Notes:
            - The file size must not exceed 5 MB.
            - Ensure that the attachment field is configured to accept attachments.
            - The 'file_bytes' should be base64 encoded before being passed to the function.
        """
        url = f"https://content.airtable.com/v0/{self.base_id}/{record_id}/{attachment_field}/uploadAttachment"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        encoded_file = base64.b64encode(file_bytes).decode("utf-8")

        payload = {
            "contentType": content_type,
            "file": encoded_file,
            "filename": filename
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=json.dumps(payload)) as response:
                if response.status == 200:
                    attachment_response = await response.json()
                    print(f"Attachment '{filename}' uploaded successfully to record '{record_id}'!")
                    return attachment_response
                else:
                    print(f"Failed to upload attachment '{filename}' to record '{record_id}'. "
                          f"Status code: {response.status}")
                    print(await response.text())
                    return None

    async def update_field(
        self,
        table_id: str,
        column_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None
    ) -> Optional[dict]:
        """
        Update the name and/or description of a field in a given table.

        Args:
            table_id (str): The ID of the table containing the field.
            column_id (str): The field (column) ID to update.
            name (str, optional): New name for the field.
            description (str, optional): New description for the field.

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

        url = f"https://api.airtable.com/v0/meta/bases/{self.base_id}/tables/{table_id}/fields/{column_id}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload: Dict[str, str] = {}
        if name:
            payload["name"] = name
        if description:
            payload["description"] = description

        async with aiohttp.ClientSession() as session:
            async with session.patch(url, headers=headers, data=json.dumps(payload)) as response:
                if response.status == 200:
                    updated_field = await response.json()
                    print(f"Field '{column_id}' updated successfully!")
                    return updated_field
                else:
                    print(f"Failed to update field '{column_id}'. Status code: {response.status}")
                    print(await response.text())
                    return None
