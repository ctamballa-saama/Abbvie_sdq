import pandas as pd
import numpy as np
import logging
import sys
# from termcolor import colored
import datetime
from dateutil.parser import parse

#Function to get all the map tables values and put it in a dict for later use
def get_map_tables(): # schema, connector
    # conn = connector.connect()
    needed_maps = {'map_subject': ['subjid', 'subject_guid'], 
                    'map_visit': ['visit_id', 'visit_nm'], 
                    'map_item': ['item_id', 'item_nm'], 
                    'map_site': ['site_id', 'sitemnemonic'],
                    'map_form': ['form_id', 'form_nm']
                    }

    return_map_df_dict = {}
    for map_nm, needed_cols in needed_maps.items():
        needed_cols = ','.join(needed_cols)
        # map_df = pd.read_sql_query(f'SELECT {needed_cols} FROM {schema}.{map_nm}', conn)
        map_df = pd.read_csv('t_cm.cvs')
        if 'subject_guid' in map_df.columns:
            map_df = map_df.rename(columns={'subject_guid': 'subj_guid'})
        return_map_df_dict[map_nm] = map_df
    
    return return_map_df_dict

def parse_date(x):
    if isinstance(x, str):
        try:
            return_val= parse(x)
        except:
            return_val = datetime.datetime.strptime('01JAN1900:12:40:25', '%d%b%Y:%H:%M:%S')
    else:
        return_val = datetime.datetime.strptime('01JAN1900:12:40:25', '%d%b%Y:%H:%M:%S')
    return return_val

def handling_missing_cols(dataF, needed_columns):
    print(f"Data has {dataF.shape} for handling missing cols")
    date_col = ['modif_dts']
    print(f"RENAME - {dataF.columns.tolist()}")
    not_present_cols = [col for col in needed_columns if col not in  dataF.columns.tolist()]
    #printing not present cols
    print(f"Columns not present for Stg_pred - {not_present_cols}")
    for col in not_present_cols:
        if col in date_col:
            dataF[col] = [datetime.datetime.utcnow() for _ in range(len(dataF))]
        else:
            dataF[col] = list(np.repeat('null', dataF.shape[0]))
    dataF = dataF[needed_columns]

    return dataF

def handle_nan(dataF):
    print(f"Data has {dataF.shape} for handling nan")
    nan_handle_cols = ['form_ix', 'itemset_ix', 'form_index', 'itemrepn', 'subjid', 'siteno', 'sitemnemonic', 'item_value', 'answer_in_text', 'subjid', 'sectionref_nm']

    for col in nan_handle_cols:
        dataF[col] = dataF[col].replace(np.inf, 'null')
        dataF[col] = dataF[col].replace(np.nan, 'null')
        dataF[col] = dataF[col].astype(str)

    return dataF            

def unflatten_df_process(unflatten_df, map_df_dict, stg_needed_columns):
    map_item_df = map_df_dict['map_item']
    map_subj_df = map_df_dict['map_subject']
    map_visit_df = map_df_dict['map_visit']
    map_site_df = map_df_dict['map_site']
    map_form_df = map_df_dict['map_form']

    #Get ITEMID using ITEMNAME from map_item_df
    print(f"Before item id processing - {unflatten_df.shape[0]}")
    item_name_dict = {item_name: item_id for item_name, item_id in zip(map_item_df['item_nm'].values, map_item_df['item_id'].values)}
    get_item_id = lambda x: item_name_dict[x] if x in item_name_dict else 0
    unflatten_df['item_id'] = unflatten_df['item_nm'].apply(get_item_id)
    
    form_name_dict = {form_name.lower(): form_id for form_name, form_id in zip(map_form_df['form_nm'].values, map_form_df['form_id'].values)}
    get_form_id = lambda x: form_name_dict[x.lower()] if x.lower() in form_name_dict else 0
    unflatten_df['form_id'] = unflatten_df['formname'].apply(get_form_id)

    print(f'Before Subj_Guid processing - {unflatten_df.shape[0]}')
    #Get SUBJ_GUID using SUBJID from map_subject_df
    if 'subj_guid' in unflatten_df.columns: 
        unflatten_df.drop(['subj_guid'], axis=1, inplace=True)
    unflatten_df['subjid'] = unflatten_df['subjid'].astype(str)
    #unflatten_df = pd.merge(unflatten_df, map_subj_df.astype(str), on='subjid')
    print(f'After Subj_Guid processing - {unflatten_df.shape[0]}')
    #Get VISIT_NM using VISIT_ID from map_visit_df
    #unflatten_df = unflatten_df.drop(['visit_nm'], axis=1, inplace=False)
    #unflatten_df = pd.merge(unflatten_df, map_visit_df, on='visit_id')
    #Visit_Nm is already present in the clinical data

    unflatten_df['formrefname'] = unflatten_df['formname']
    unflatten_df['answer_in_text'] = unflatten_df['item_value']
    unflatten_df = handling_missing_cols(unflatten_df, stg_needed_columns)
    unflatten_df = handle_nan(unflatten_df)
    unflatten_df['modif_dts'] = unflatten_df['modif_dts'].apply(parse_date)
    print(f'After processing contains {unflatten_df.shape[0]} records')

    return unflatten_df