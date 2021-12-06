#!/usr/bin/env python
# coding: utf-8

import os
import sys
import traceback as tb
import boto3
from io import BytesIO


class QueryTemplate:
    """Templates for querying data from different sys"""
    GETLASTBATCH = """
    SELECT {columns} FROM {SCHEMA_DATALOAD_AUDIT}.{DATALOAD_AUDIT_TABLE} 
    WHERE (batch_id, study_id) IN (
        SELECT MAX(batch_id), study_id  FROM {SCHEMA_DATALOAD_AUDIT}.{DATALOAD_AUDIT_TABLE} WHERE study_status = 'ACTIVE' GROUP BY study_id
    )
    AND (dataload_status <> 'RUNNING' or dataload_status IS NULL);
    """
    GETSTUDYLASTBATCH = """
    SELECT {columns} FROM {SCHEMA_DATALOAD_AUDIT}.{DATALOAD_AUDIT_TABLE} 
    WHERE batch_id IN (
        SELECT MAX(batch_id) FROM {SCHEMA_DATALOAD_AUDIT}.{DATALOAD_AUDIT_TABLE} WHERE study_status = 'ACTIVE' AND study_id = '{study_id}' GROUP BY study_id
    )
    AND (dataload_status <> 'RUNNING' or dataload_status IS NULL);
    """
        
    GETFAILEDTABLES = """
    SELECT source_tablename FROM {SCHEMA_DATALOAD_AUDIT}.{DATALOAD_DETAIL_TABLE}
    WHERE batch_id = {batch_id} AND study_id = '{study_id}' AND load_status = 'FAILED';
    """
    GETDETAILTABLES = """
    SELECT * FROM {SCHEMA_DATALOAD_AUDIT}.{DATALOAD_DETAIL_TABLE}
    WHERE batch_id = {batch_id} AND study_id = '{study_id}';
    """
    
    INSERTAUDITRUNNING = """
    INSERT INTO {SCHEMA_DATALOAD_AUDIT}.{DATALOAD_AUDIT_TABLE}({columns})
    VALUES ({values});
    """
    
    GETEXISTEDMETADATA = """
    SELECT * FROM {schemaname}.{tablename};
    """
    
    #data {'schemaname': 'test', 'tablename': 'log', 'columns': 'col1,col2,col3', 'values': ' 'test', 'dummy', 1 '}
    DELETEVALUES = """
    DELETE FROM {schemaname}.{tablename} 
    WHERE ({columns}) in ({values});
    """
    
    INSERTVALUES = """
    INSERT INTO {schemaname}.{tablename}({columns})
    VALUES {values};
    """

    UPDATEAUDITTABLE = """
    UPDATE {schemaname}.{tablename} 
    SET {column} = '{status}'
    WHERE {column} = 'RUNNING' AND batch_id = {batch_id} AND study_id = '{study_id}';
    """
    
    
class ConstantVars:
    
    def __init__(self, config={}):
        
        ROOT_DIR = os.path.abspath(os.path.dirname(__file__))

        #schema name
        self.SCHEMA_DATALOAD_AUDIT = config.get('DB_DATAPIPELINE_SCHEMA') or os.environ.get("SCHEMA_DATALOAD_AUDIT", "common") 
        self.SCHEMA_METADATA = config.get('SCHEMA_METADATA') or os.environ.get("SCHEMA_METADATA", "common")

        #tablename
        self.DATALOAD_AUDIT_TABLE = config.get('DB_DATALOAD_AUDIT') or os.environ.get("DB_DATALOAD_AUDIT", "dataload_audit")
        self.DATALOAD_DETAIL_TABLE = config.get('DB_DATALOAD_DETAIL') or os.environ.get("DB_DATALOAD_DETAIL", "dataload_detail_audit")
        self.SUBJECT_COUNT_TABLE = config.get('SUBJECT_COUNT_TABLE') or os.environ.get("SUBJECT_COUNT_TABLE", "count_record")

        self.CLINICALDATA_LIST = config.get('CLINICALDATA_LIST') or os.environ.get("CLINICALDATA_LIST", "beetrk,lb,clb,ec,mh,favsd,cecisr,fafuc,dm,ds,ae,cm,r_trig,sv,vs,slopd,mbmib,lboxy,cesod,ie,hohcu")

        #column name
        self.SUBJECTID = config.get('SUBJECTID') or os.environ.get("SUBJECTID", "subjid")


        self.SOURCE_SYSTEM = config.get('SOURCE_SYSTEM') or os.environ.get("SOURCE_SYSTEM", "RAVE")

        ##formname mapper #?

        #each form format 
        self.MAP_FORM_MAPPER = { #md_irv_form_revs
            #{attribute_name: column_name}, attribute name is original dataset column name, column name is our db colname
            'target_tablename': "map_form", 
            'column_mapper': {
                                'inform': {'FORMID': 'form_id', 'FORMREV': 'form_rev', 'FORMNAME': 'form_nm'},  #empty as defualt to load all data 
                                'rave': {'OID': 'form_id', 'UNK': 'form_rev', 'Name': 'form_nm'},  #empty as defualt to load all data 
                                },
            'primary_key': ["form_id"], #should not empty for insert/upadate logic
        }

        self.MAP_ITEM_MAPPER = {
            'target_tablename': 'map_item',
            #{attribute_name: column_name}, attribute name is original dataset column name, column name is our db colname
            'column_mapper': {
                                'inform': {'ITEMID': 'item_id', 'ITEMREFNAME': 'item_nm', 'ITEMQUESTION': 'question_text'}, #empty as defualt to load all data
                                'rave': {'OID': 'item_id', 'Name': 'item_nm', 'SASLabel': 'question_text'}, #empty as defualt to load all data
                                },
            'primary_key': ["item_id"], #should not empty for insert/upadate logic
        }

        self.MAP_SUBJECT_MAPPER = {
            'target_tablename': 'map_subject',
            #{attribute_name: column_name}, attribute name is original dataset column name, column name is our db colname
            'column_mapper': {
                                'inform':{'SUBJECTNUMBERSTR': 'subjid', 'SUBJECTID': 'subject_id', 'SUBJECTREV': 'subject_rev', 'SITEID': 'site_id', 'GUID': 'subject_guid'},  #empty as defualt to load all data
                                'rave':{'subject_key': 'subjid', 'UNK': 'subject_rev', 'site_key': 'site_id', '__hash': 'subject_guid'},  #empty as defualt to load all data
                                },
            'primary_key': ["subject_id"], #should not empty for insert/upadate logic
        }
        
        self.IRV_CUR_SUBJECT_MAPPER = {
            'target_tablename': 'map_subject',
            #{attribute_name: column_name}, attribute name is original dataset column name, column name is our db colname
            'column_mapper': {'SUBJECTNUMBERSTR': 'subjid', 'SUBJECTID': 'subject_id', 'SUBJECTREV': 'subject_rev', 'SITEID': 'site_id', 'GUID': 'subject_guid'},  #empty as defualt to load all data
            'primary_key': ["subject_id"], #should not empty for insert/upadate logic
        }
 
        self.RD_DATADICTIONARY_MAPPER = {
            'target_tablename': None,
            'column_mapper': {'inform': {'FORMID': 'formid', 'FORMNAME': 'formname', 'FORMREFNAME': 'formrefname', 'CHILDITEMID': 'childitemid', 'ITEMID': 'itemid', 'SECTIONREFNAME': 'sectionrefname', 'ITEMSET': 'itemset', 'COLUMNDBTYPE': 'columndbtype', 'ITEMQUESTION': 'itemquestion', 'ITEMREFNAME': 'itemrefname', 'CHILDITEMREFNAME': 'childitemrefname'},
                                'rave': {}},
        }
        
        self.QUERY_MAPPER = {
            'target_tablename': 'map_query',
            'column_mapper': {'QUERYCOUNT': 'querycount', 'QUERYID': 'queryid', 'QUERYTIME': 'querytime', 'QUERYUSERID': 'queryuserid', 'QUERYHIST': 'queryhist', 'CONTEXTID': 'contextid', 'SUBJECTVISITID': 'subjectvisitid', 'SUBJECTID': 'subjectid', 'STUDYID': 'studyid', 'SITEID': 'siteid', 'STUDYVERSIONID': 'studyversionid', 'VISITID': 'visitid', 'VISITREV': 'visitrev', 'VISITINDEX': 'visitindex', 'VISITSTUDYVERSIONID': 'visitstudyversionid', 'FORMID': 'formid', 'FORMREV': 'formrev', 'FORMINDEX': 'formindex', 'SECTIONID': 'sectionid', 'SECTIONREV': 'sectionrev', 'ITEMSETID': 'itemsetid', 'ITEMSETREV': 'itemsetrev', 'ITEMSETINDEX': 'itemsetindex', 'ITEMID': 'itemid', 'ITEMREV': 'itemrev', 'QREVS': 'qrevs', 'MINQUERYREV': 'minqueryrev', 'MAXQUERYREV': 'maxqueryrev', 'QUERYTYPE': 'querytype', 'QTYPEAUTO': 'qtypeauto', 'QTYPEMANUAL': 'qtypemanual', 'QTYPECONFLICT': 'qtypeconflict', 'QUERYSTATE': 'querystate', 'QREISSUED': 'qreissued', 'QCANDIDATE': 'qcandidate', 'QOPENED': 'qopened', 'QANSWERED': 'qanswered', 'QCLOSED': 'qclosed', 'QDELETED': 'qdeleted', 'QUERYGROUP': 'querygroup', 'QUERYDATA': 'querydata', 'RULEITEMID': 'ruleitemid', 'RULEID': 'ruleid', 'CONFLICTSTATE': 'conflictstate', 'INFORMPARTIALURL_QUERY': 'informpartialurl_query', 'QDAYSOPENTOANSWER': 'qdaysopentoanswer', 'QDAYSANSWERTOCLOSE': 'qdaysanswertoclose', 'QDAYSOPENTOCLOSE': 'qdaysopentoclose', 'QCOUNTREISSUED': 'qcountreissued', 'QMINREISSUED': 'qminreissued', 'QMAXREISSUED': 'qmaxreissued', 'QCOUNTCANDIDATE': 'qcountcandidate', 'QMINCANDIDATE': 'qmincandidate', 'QMAXCANDIDATE': 'qmaxcandidate', 'QCOUNTOPENED': 'qcountopened', 'QMINOPENED': 'qminopened', 'QMAXOPENED': 'qmaxopened', 'QCOUNTANSWERED': 'qcountanswered', 'QMINANSWERED': 'qminanswered', 'QMAXANSWERED': 'qmaxanswered', 'QCOUNTCLOSED': 'qcountclosed', 'QMINCLOSED': 'qminclosed', 'QMAXCLOSED': 'qmaxclosed', 'QCOUNTDELETED': 'qcountdeleted', 'QMINDELETED': 'qmindeleted', 'QMAXDELETED': 'qmaxdeleted', 'QORIGUSER': 'qoriguser', 'QSTATUSTIME': 'qstatustime', 'QDAYSINSTATE': 'qdaysinstate', 'FIRSTREISSUEDTEXT': 'firstreissuedtext', 'LASTREISSUEDTEXT': 'lastreissuedtext', 'FIRSTCANDIDATETEXT': 'firstcandidatetext', 'LASTCANDIDATETEXT': 'lastcandidatetext', 'FIRSTOPENEDTEXT': 'firstopenedtext', 'LASTOPENEDTEXT': 'lastopenedtext', 'FIRSTANSWEREDTEXT': 'firstansweredtext', 'LASTANSWEREDTEXT': 'lastansweredtext', 'FIRSTCLOSEDTEXT': 'firstclosedtext', 'LASTCLOSEDTEXT': 'lastclosedtext', 'FIRSTDELETEDTEXT': 'firstdeletedtext', 'LASTDELETEDTEXT': 'lastdeletedtext'},
            'primary_key': ["queryid"]
        }
        
        self.MAP_ACTIVATED_FORMS_MAPPER = {
            'target_tablename': 'map_od_rt_activated_forms',
            'column_mapper': {'inform':{'SUBJECTVISITID': 'subjectvisitid', 'SUBJECTID': 'subjectid', 'SITEID': 'siteid', 'VISITID': 'visitid', 'VISITINDEX': 'visitindex', 'FORMID': 'formid', 'FORMREV': 'formrev', 'FORMINDEX': 'formindex'},
                                'rave': {}},
            'primary_key': ['subjectvisitid', 'subjectid', 'siteid', 'visitid', 'visitindex', 'formid', 'formrev', 'formindex']
        }
        
        self.MAP_VISIT_MAPPER = {
            'target_tablename': 'map_visit',
            'column_mapper': {
                                'inform': {'VISITID': 'visit_id', 'VISITREFNAME': 'visit_nm'},
                                'rave': {'OID': 'visit_id', 'Name': 'visit_nm'},
                                },
            'primary_key': ['visit_id']
        }
        
        self.MAP_SITE_MAPPER = {
            'target_tablename': 'map_site',
            'column_mapper': {
                                'inform': {'SITEID': 'site_id', 'SITENAME': 'site_nm', 'SITECOUNTRY': 'site_country', 'SITEMNEMONIC': 'sitemnemonic'},
                                'rave': {'oid': 'site_id', 'name': 'site_nm', 'sitecountry': 'site_country', 'studysitenumber': 'sitemnemonic'},
                                },
            'primary_key': ['site_id']
        }
        
        self.MAP_SECTION_MAPPER = {
            'target_tablename': 'map_section',
            'column_mapper': {'inform': {'SECTIONID': 'sectionid', 'SECTIONREV': 'sectionrev', 'SECTIONREFNAME': 'sectionrefname', 'REPEATINGSECTION': 'repeatingsection'},
                                'rave': {}},
            'primary_key': ['sectionid', 'sectionrev', 'sectionrefname']
        }  
        
        
        self.BEETRK_MAPPER= {
            'column_mapper': {'STUDYNAME': 'STUDYNAME', 'SITECOUNTRY': 'SITECOUNTRY', 'SITEMNEMONIC': 'SITEMNEMONIC', 'SITEID': 'SITEID', 'SUBJECTNUMBERSTR': 'SUBJECTNUMBERSTR', 'VISITREFNAME': 'VISITREFNAME', 'VISITINDEX': 'VISITINDEX', 'VISITID': 'VISITID', 'DOV': 'DOV', 'FORMREFNAME': 'FORMREFNAME', 'FORMID': 'FORMID', 'FORMIDX': 'FORMIDX', 'FORMINDEX': 'FORMINDEX', 'ITEMSETIDX': 'ITEMSETIDX', 'ITEMSETINDEX': 'ITEMSETINDEX', 'ITEMSETID': 'ITEMSETID', 'DATEDATACHANGED': 'DATEDATACHANGED', 'AUDIT_START_DATE': 'AUDIT_START_DATE', 'BEOCCUR_001': 'BEOCCUR_001', 'CO_BECOM_001': 'CO_BECOM_001', 'BEOCCUR_001_ND': 'BEOCCUR_001_ND', 'SUPPBE_ETRKDOR_001': 'SUPPBE_ETRKDOR_001', 'BESCAT_001': 'BESCAT_001', 'BEDTC_001': 'BEDTC_001', 'BEREFID_001': 'BEREFID_001', 'SUBJECTID': 'SUBJECTID', 'BEPARTY_001': 'BEPARTY_001', 'AUDIT_ACTION': 'AUDIT_ACTION', 'BEOCCUR_005': 'BEOCCUR_005', 'CO_BECOM_005': 'CO_BECOM_005', 'BESCAT_005': 'BESCAT_005', 'BEREFID_005': 'BEREFID_005'}}

        self.LB_MAPPER= {
            'column_mapper': {'inform': {}, 
                                'rave': {}
                                }
                        }
        self.CLB_MAPPER= {
            'column_mapper': {'STUDYNAME': 'STUDYNAME', 'SITECOUNTRY': 'SITECOUNTRY', 'SITEMNEMONIC': 'SITEMNEMONIC', 'SITEID': 'SITEID', 'SUBJECTNUMBERSTR': 'SUBJECTNUMBERSTR', 'VISITREFNAME': 'VISITREFNAME', 'VISITINDEX': 'VISITINDEX', 'VISITID': 'VISITID', 'DOV': 'DOV', 'FORMREFNAME': 'FORMREFNAME', 'FORMID': 'FORMID', 'FORMIDX': 'FORMIDX', 'FORMINDEX': 'FORMINDEX', 'ITEMSETIDX': 'ITEMSETIDX', 'ITEMSETINDEX': 'ITEMSETINDEX', 'ITEMSETID': 'ITEMSETID', 'DATEDATACHANGED': 'DATEDATACHANGED', 'AUDIT_START_DATE': 'AUDIT_START_DATE', 'LBDTC_003_DTS': 'LBDTC_003_DTS', 'SUBJECTID': 'SUBJECTID', 'AUDIT_ACTION': 'AUDIT_ACTION', 'SUBJID': 'SUBJID', 'VISITNAM': 'VISITNAM', 'FORMNAME': 'FORMNAME', 'ITEMREPN': 'ITEMREPN', 'MODIFYTS': 'MODIFYTS', 'LBDAT_DTS': 'LBDAT_DTS'}}

        self.EC_MAPPER= {
            'column_mapper': {'inform': {}, 
                                'rave': {}
                                }
                        }
        self.MH_MAPPER= {
            'column_mapper': {'inform': {}, 
                                'rave': {}
                                }
                        }
        self.FAVSD_MAPPER= {
            'column_mapper': {'STUDYNAME': 'STUDYNAME', 'SITECOUNTRY': 'SITECOUNTRY', 'SITEMNEMONIC': 'SITEMNEMONIC', 'SITEID': 'SITEID', 'SUBJECTNUMBERSTR': 'SUBJECTNUMBERSTR', 'VISITREFNAME': 'VISITREFNAME', 'VISITINDEX': 'VISITINDEX', 'VISITID': 'VISITID', 'DOV': 'DOV', 'FORMREFNAME': 'FORMREFNAME', 'FORMID': 'FORMID', 'FORMIDX': 'FORMIDX', 'FORMINDEX': 'FORMINDEX', 'ITEMSETIDX': 'ITEMSETIDX', 'ITEMSETINDEX': 'ITEMSETINDEX', 'ITEMSETID': 'ITEMSETID', 'DATEDATACHANGED': 'DATEDATACHANGED', 'AUDIT_START_DATE': 'AUDIT_START_DATE', 'Y_FADTC_012_DTS': 'Y_FADTC_012_DTS', 'X_VSDSDAY_012': 'X_VSDSDAY_012', 'R_VSDTEST_012': 'R_VSDTEST_012', 'Y_FAORRES_012': 'Y_FAORRES_012', 'Y_FAORRESU_012': 'Y_FAORRESU_012', 'CETERM_011': 'CETERM_011', 'CEOCCUR_011': 'CEOCCUR_011', 'X_SUPPCE_SONGO_011': 'X_SUPPCE_SONGO_011', 'X_SUPPCE_IONGO_011': 'X_SUPPCE_IONGO_011', 'CEENDTC_011': 'CEENDTC_011', 'FAORRES_FPMD_011': 'FAORRES_FPMD_011', 'X_SUPPFA_FPDAT_011': 'X_SUPPFA_FPDAT_011', 'X_SUPPFA_ONGO_011': 'X_SUPPFA_ONGO_011', 'SUBJECTID': 'SUBJECTID', 'CETERM1_011': 'CETERM1_011', 'CEOCCUR1_011': 'CEOCCUR1_011', 'CEENDTC1_011': 'CEENDTC1_011', 'FAORRES_MEDTFVPN_011': 'FAORRES_MEDTFVPN_011', 'X_FAORRES_FPDAT_011': 'X_FAORRES_FPDAT_011', 'X_ONGO_011': 'X_ONGO_011', 'FAORRES_FPDAT_011': 'FAORRES_FPDAT_011', 'AUDIT_ACTION': 'AUDIT_ACTION'}}

        self.CECISR_MAPPER= {
            'column_mapper': {}}

        self.FAFUC_MAPPER= {
            'column_mapper': {}}

        self.DM_MAPPER= {
            'column_mapper': {}}

        self.DS_MAPPER= {
            'column_mapper': {'STUDYNAME': 'STUDYNAME', 'SITECOUNTRY': 'SITECOUNTRY', 'SITEMNEMONIC': 'SITEMNEMONIC', 'SITEID': 'SITEID', 'SUBJECTNUMBERSTR': 'SUBJECTNUMBERSTR', 'VISITREFNAME': 'VISITREFNAME', 'VISITINDEX': 'VISITINDEX', 'VISITID': 'VISITID', 'DOV': 'DOV', 'FORMREFNAME': 'FORMREFNAME', 'FORMID': 'FORMID', 'FORMIDX': 'FORMIDX', 'FORMINDEX': 'FORMINDEX', 'ITEMSETIDX': 'ITEMSETIDX', 'ITEMSETINDEX': 'ITEMSETINDEX', 'ITEMSETID': 'ITEMSETID', 'DATEDATACHANGED': 'DATEDATACHANGED', 'AUDIT_START_DATE': 'AUDIT_START_DATE', 'SUPPDS_DSRANGRP_001': 'SUPPDS_DSRANGRP_001', 'DSSTDTC_001_DTS': 'DSSTDTC_001_DTS', 'DSDECOD_001': 'DSDECOD_001', 'DSTERM_001': 'DSTERM_001', 'SUPPDS_DSPHASE_001': 'SUPPDS_DSPHASE_001', 'DSSTDTC_001': 'DSSTDTC_001', 'DSREFID_001': 'DSREFID_001', 'SUPPDS_DSENRGRP_001': 'SUPPDS_DSENRGRP_001', 'SUBJECTID': 'SUBJECTID', 'AUDIT_ACTION': 'AUDIT_ACTION', 'SUBJID': 'SUBJID', 'VISITNAM': 'VISITNAM', 'FORMNAME': 'FORMNAME', 'ITEMREPN': 'ITEMREPN', 'MODIFYTS': 'MODIFYTS', 'DSSTDAT': 'DSSTDAT', 'DSSTDAT_DTS': 'DSSTDAT_DTS', 'DSDECOD': 'DSDECOD', 'DSREFID': 'DSREFID', 'DSPHASE': 'DSPHASE', 'DSTERM': 'DSTERM'}}

        self.AE_MAPPER= {
            'column_mapper': {'inform': {}, 
                                'rave': {}
                                }
                        }

        self.CM_MAPPER= {
            'column_mapper': {'inform': {}, 
                                'rave': {}
                                }
                        }

        self.R_TRIG_MAPPER= {
            'column_mapper': {'STUDYNAME': 'STUDYNAME', 'SITECOUNTRY': 'SITECOUNTRY', 'SITEMNEMONIC': 'SITEMNEMONIC', 'SITEID': 'SITEID', 'SUBJECTNUMBERSTR': 'SUBJECTNUMBERSTR', 'VISITREFNAME': 'VISITREFNAME', 'VISITINDEX': 'VISITINDEX', 'VISITID': 'VISITID', 'DOV': 'DOV', 'FORMREFNAME': 'FORMREFNAME', 'FORMID': 'FORMID', 'FORMIDX': 'FORMIDX', 'FORMINDEX': 'FORMINDEX', 'ITEMSETIDX': 'ITEMSETIDX', 'ITEMSETINDEX': 'ITEMSETINDEX', 'ITEMSETID': 'ITEMSETID', 'DATEDATACHANGED': 'DATEDATACHANGED', 'AUDIT_START_DATE': 'AUDIT_START_DATE', 'R_TRIGRESP9_001': 'R_TRIGRESP9_001', 'R_TRIGRESP10_001': 'R_TRIGRESP10_001', 'R_TRIGRESP2_001': 'R_TRIGRESP2_001', 'R_TRIGRESP3_001': 'R_TRIGRESP3_001', 'SUBJECTID': 'SUBJECTID', 'AUDIT_ACTION': 'AUDIT_ACTION'}}

        self.SV_MAPPER= {
            'column_mapper': {}}

        self.VS_MAPPER= {
            'column_mapper': {'STUDYNAME': 'STUDYNAME', 'SITECOUNTRY': 'SITECOUNTRY', 'SITEMNEMONIC': 'SITEMNEMONIC', 'SITEID': 'SITEID', 'SUBJECTNUMBERSTR': 'SUBJECTNUMBERSTR', 'VISITREFNAME': 'VISITREFNAME', 'VISITINDEX': 'VISITINDEX', 'VISITID': 'VISITID', 'DOV': 'DOV', 'FORMREFNAME': 'FORMREFNAME', 'FORMID': 'FORMID', 'FORMIDX': 'FORMIDX', 'FORMINDEX': 'FORMINDEX', 'ITEMSETIDX': 'ITEMSETIDX', 'ITEMSETINDEX': 'ITEMSETINDEX', 'ITEMSETID': 'ITEMSETID', 'DATEDATACHANGED': 'DATEDATACHANGED', 'AUDIT_START_DATE': 'AUDIT_START_DATE', 'VSDTC_001': 'VSDTC_001', 'VSDTC_001_DTS': 'VSDTC_001_DTS', 'SUBJECTID': 'SUBJECTID', 'AUDIT_ACTION': 'AUDIT_ACTION'}}

        self.SLOPD_MAPPER= {
            'column_mapper': {}}

        self.MBMIB_MAPPER= {
            'column_mapper': {}}

        self.LBOXY_MAPPER= {
            'column_mapper': {}}

        self.CESOD_MAPPER= {
            'column_mapper': {'STUDYNAME': 'STUDYNAME', 'SITECOUNTRY': 'SITECOUNTRY', 'SITEMNEMONIC': 'SITEMNEMONIC', 'SITEID': 'SITEID', 'SUBJECTNUMBERSTR': 'SUBJECTNUMBERSTR', 'VISITREFNAME': 'VISITREFNAME', 'VISITINDEX': 'VISITINDEX', 'VISITID': 'VISITID', 'DOV': 'DOV', 'FORMREFNAME': 'FORMREFNAME', 'FORMID': 'FORMID', 'FORMIDX': 'FORMIDX', 'FORMINDEX': 'FORMINDEX', 'ITEMSETIDX': 'ITEMSETIDX', 'ITEMSETINDEX': 'ITEMSETINDEX', 'ITEMSETID': 'ITEMSETID', 'DATEDATACHANGED': 'DATEDATACHANGED', 'AUDIT_START_DATE': 'AUDIT_START_DATE', 'SUBJECTID': 'SUBJECTID', 'Y_CEDTC_006': 'Y_CEDTC_006', 'FAORRES_FSSDTC_006': 'FAORRES_FSSDTC_006', 'X_FAONGO_006': 'X_FAONGO_006', 'FAORRES_LSRDTC_006': 'FAORRES_LSRDTC_006', 'CETERM1_006': 'CETERM1_006', 'CETERM_006': 'CETERM_006', 'CELLT_006': 'CELLT_006', 'CEDECOD_006': 'CEDECOD_006', 'CEHLT_006': 'CEHLT_006', 'CEHLGT_006': 'CEHLGT_006', 'CESOC_006': 'CESOC_006', 'AUDIT_ACTION': 'AUDIT_ACTION'}}

        self.IE_MAPPER= {
            'column_mapper': {'STUDYNAME': 'STUDYNAME', 'SITECOUNTRY': 'SITECOUNTRY', 'SITEMNEMONIC': 'SITEMNEMONIC', 'SITEID': 'SITEID', 'SUBJECTNUMBERSTR': 'SUBJECTNUMBERSTR', 'VISITREFNAME': 'VISITREFNAME', 'VISITINDEX': 'VISITINDEX', 'VISITID': 'VISITID', 'DOV': 'DOV', 'FORMREFNAME': 'FORMREFNAME', 'FORMID': 'FORMID', 'FORMIDX': 'FORMIDX', 'FORMINDEX': 'FORMINDEX', 'ITEMSETIDX': 'ITEMSETIDX', 'ITEMSETINDEX': 'ITEMSETINDEX', 'ITEMSETID': 'ITEMSETID', 'DATEDATACHANGED': 'DATEDATACHANGED', 'AUDIT_START_DATE': 'AUDIT_START_DATE', 'SUBJECTID': 'SUBJECTID', 'IESPID_001': 'IESPID_001', 'IETEST_001': 'IETEST_001', 'IEORRES_001': 'IEORRES_001', 'SUPPIE_IEDESC_001': 'SUPPIE_IEDESC_001', 'AUDIT_ACTION': 'AUDIT_ACTION', 'SUBJID': 'SUBJID', 'VISITNAM': 'VISITNAM', 'FORMNAME': 'FORMNAME', 'ITEMREPN': 'ITEMREPN', 'MODIFYTS': 'MODIFYTS', 'IESPID': 'IESPID', 'IETEST': 'IETEST', 'IEORRES': 'IEORRES', 'IEDESC': 'IEDESC'}}

        self.HOHCU_MAPPER= {
            'column_mapper': {'STUDYNAME': 'STUDYNAME', 'SITECOUNTRY': 'SITECOUNTRY', 'SITEMNEMONIC': 'SITEMNEMONIC', 'SITEID': 'SITEID', 'SUBJECTNUMBERSTR': 'SUBJECTNUMBERSTR', 'VISITREFNAME': 'VISITREFNAME', 'VISITINDEX': 'VISITINDEX', 'VISITID': 'VISITID', 'DOV': 'DOV', 'FORMREFNAME': 'FORMREFNAME', 'FORMID': 'FORMID', 'FORMIDX': 'FORMIDX', 'FORMINDEX': 'FORMINDEX', 'ITEMSETIDX': 'ITEMSETIDX', 'ITEMSETINDEX': 'ITEMSETINDEX', 'ITEMSETID': 'ITEMSETID', 'DATEDATACHANGED': 'DATEDATACHANGED', 'AUDIT_START_DATE': 'AUDIT_START_DATE', 'SUBJECTID': 'SUBJECTID', 'SUPPHO_HCUIDIS_002': 'SUPPHO_HCUIDIS_002', 'HOTERM_002': 'HOTERM_002', 'X_HOTERM_HCUTERM_002': 'X_HOTERM_HCUTERM_002', 'AUDIT_ACTION': 'AUDIT_ACTION'}}
    
class Config:
    ALLOWED_EXTENSIONS = 'csv,xlsx'
    ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
    print(ROOT_DIR)
    #db conn
    DB_DATAPIPELINE_HOST = os.environ.get("DB_DATAPIPELINE_HOST", "")
    DB_DATAPIPELINE_PORT = os.environ.get("DB_DATAPIPELINE_PORT", "")
    DB_DATAPIPELINE_DBNAME = os.environ.get("DB_DATAPIPELINE_DBNAME", "")
    DB_DATAPIPELINE_SCHEMA = os.environ.get("DB_DATAPIPELINE_SCHEMA", "")
    DB_DATAPIPELINE_USER = os.environ.get("DB_DATAPIPELINE_USER", "")
    DB_DATAPIPELINE_PW = os.environ.get("DB_DATAPIPELINE_PW", "")
    
    # [aws]s3 
    S3_PREFIX = os.environ.get("S3_PREFIX", "")
    S3_BUCKET = os.environ.get("S3_BUCKET", "")
    S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "")
    S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "")
    S3_REGION = os.environ.get("S3_REGION", "us-east-2")    
    
    
    
class DevelopmentConfig(Config):
    env = 'dev'
