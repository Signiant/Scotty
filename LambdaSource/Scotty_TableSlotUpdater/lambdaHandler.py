#! python3
import boto3
import time
from pprint import pprint


def updateBot(lex, updatedSlotVersion):
    bot = lex.get_bot(
        name='Scotty',
        versionOrAlias="$LATEST"
    )
    intentVersion = []
    intentName = []
    for intent in bot['intents']:
        newIntent = lex.get_intent(name=intent['intentName'], version="$LATEST")
        for i in range(len(newIntent['slots'])):
            if "table" == newIntent['slots'][i]['name']:
                newIntent['slots'][i]['slotTypeVersion'] = updatedSlotVersion
                putIntent(lex, newIntent)
                version = publishIntent(lex, newIntent)
                intentVersion.append({'intentName': intent['intentName'], 'intentVersion': version})
                intentName.append(intent['intentName'])

        if intent['intentName'] not in intentName:
            intentVersion.append({'intentName': intent['intentName'], 'intentVersion': intent['intentVersion']})
    # pprint(intentVersion)
    checksum = putbot(lex, bot, intentVersion)
    return publishbot(lex, bot, checksum)


def putIntent(lex, intents):
    lex.put_intent(
        name=intents['name'],
        description=intents['description'],
        slots=intents['slots'],
        sampleUtterances=intents['sampleUtterances'],
        dialogCodeHook=intents['dialogCodeHook'],
        fulfillmentActivity=intents['fulfillmentActivity'],
        checksum=intents['checksum']
    )



def publishIntent(lex, intent):
    newIntent = lex.get_intent(
        name=intent['name'],
        version="$LATEST"
    )

    response = lex.create_intent_version(
        name=intent['name'],
        checksum=newIntent.get('checksum')
    )
    return response['version']


def putbot(lex, bot, intent):
    response = lex.put_bot(
        name=bot['name'],
        description=bot['description'],
        intents=intent,
        clarificationPrompt=bot['clarificationPrompt'],
        abortStatement=bot['abortStatement'],
        idleSessionTTLInSeconds=60,
        voiceId="Ivy",
        processBehavior="BUILD",
        locale="en-US",
        childDirected=False,
        createVersion=False,
        checksum=bot.get("checksum")
    )
    bot_status = response.get('status')
    checksum = response.get('checksum')
    # Wait for BOT status to be READY
    while 'READY' not in bot_status:
        bot = lex.get_bot(
            name=bot['name'],
            versionOrAlias='$LATEST'
        )
        bot_status = bot.get('status')
        checksum = bot.get('checksum')
        print('   Not ready yet...')
        time.sleep(5)
    return checksum


def publishbot(lex, bot, checksum):
    print('Publishing new Bot Version')
    result = False
    response = lex.create_bot_version(name=bot['name'], checksum=checksum)
    if 'ResponseMetadata' in response and response['ResponseMetadata']['HTTPStatusCode'] == 201:
        result = True
    return result


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
    # pprint(set_table_name)
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
        updatedSlotVersion = lex.create_slot_type_version(
            name="table",
            checksum=slot.get('checksum')
        )['version']

        if updateBot(lex, updatedSlotVersion):
            print("Table List has been updated!")
        else:
            print("The bot couldnt be updated!")
    else:
        print("No change were made to the slots")


if __name__ == "__main__":
    lambda_handler({}, None)
