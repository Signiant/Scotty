#! python3
import boto3
import argparse

from pprint import pprint


# Updating the existing slot if the any changes has occured in Dynamo DB
def lambda_handler(event, context):  # event, context

    client = boto3.client("dynamodb")
    paginator = client.get_paginator('list_tables')
    # get all the list of table in the current environment
    pages = paginator.paginate()
    tablePages = []
    for page in pages:
        tablePages.append(page['TableNames'])

    tablelist = []
    # Creating a existing table
    for List in tablePages:
        for table in List:
            tablelist.append(table)
    # coverting the list to set
    set_table_name = set(tablelist)
    pprint(set_table_name)
    lex = boto3.client('lex-models')
    # Getting the current slot Type for tables
    current_slot = lex.get_slot_type(
        name="table",
        version="$LATEST"
    )

    #  creating a set of existing table in the slot type
    table_in_slot = set(current_slot['enumerationValues'][0]['synonyms'])

    # A union of tables in current table in dynamoDb to table name in slot type
    # difference = set of table that are not in table in slot type
    # addition is the opposite

    difference = table_in_slot - set_table_name
    Addition = set_table_name - table_in_slot
    Number_of_change = len(difference)
    Number_of_add = len(Addition)

    # if the number of changes in a table is greater than 0: update the current list in slot type
    if Number_of_change is not 0 or Number_of_add is not 0:
        response = lex.put_slot_type(
            name="table",
            description="tables in dynamodb",
            enumerationValues=[
                {
                    "value": "table",
                    "synonyms": tablelist
                }
            ],
            valueSelectionStrategy='TOP_RESOLUTION',
            checksum=current_slot.get('checksum'),
            createVersion=False
        )

        slot = lex.get_slot_type(
            name="table",
            version="$LATEST"
        )
        responses_slot = lex.create_slot_type_version(
            name="table",
            checksum=slot.get('checksum')
        )
        pprint("Table List has been updated!")
    else:
        print("No change were made to the slots")


if __name__ == "__main__":
    lambda_handler({}, None)
