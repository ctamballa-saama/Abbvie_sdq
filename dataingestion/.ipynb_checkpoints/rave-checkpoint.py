import pandas as pd

def unflatten(self, clinical_dict, status= None, limit_df=None):
        # schema = self.schema_name
        # connector = self.sdq_connector
        
        data_pro_config = self.config['data_preprocess']

        adpm_df = pd.DataFrame()
        base_cols = data_pro_config['base_cols'].split(',')
        needed_domains = data_pro_config['needed_domains'].split(',')
        stg_needed_columns = self.config['stg_pred']['db_cols'].split(',')
        base_cols_rename = ast.literal_eval(data_pro_config['rename_columns'])
        for domain in clinical_dict.keys():
            logger.info(f"Current Domain processing - {domain}")
            dataF = clinical_dict[domain]
            logger.info(f"Data for {domain} - {dataF.shape}")
            data_columns = dataF.columns.tolist()
            logger.debug(
                f"Columns list before processing for domain-{domain} - {dataF.columns.tolist()}")

            # String processing domain_name
            # Eg: convert sm_ae201 to AE
            domain = domain.upper()
            int_index_list = [domain.index(word)
                              for word in domain if word.isdigit()]
            if len(int_index_list) > 0:
                int_index = min(int_index_list)
                domain = domain[:int_index]
            domain_name = domain.split('_')[1].upper()
            domain_name = re.sub("\d+", "", domain_name)
            logger.info(f"Current Processing Domain - {domain_name}")
            #:TODO Whether should handle lb003, trig separately

            #Get a sample of the dataframe for testing processing
            if limit_df != None:
                if dataF.shape[0] > limit_df:
                    dataF = dataF.sample(limit_df)
            
            #:TODO Is there any different type of data in rave like
            #vol2/ VOl3 in inform

            #Checking whether SUBJECTNUMBER column is present in the domain data
            if 'Subject' not in data_columns:
                logger.warning(f"One of the Needed base column - Subject not in the {domain} file, skipping")
                continue

            #Checking whether the data has records or not
            if dataF.shape[0] == 0:
                logger.warning(f"{domain} file doesnt have any records, skipping this file")
                continue
            
            #Checking whether the domain is needed to be processed
            if domain_name not in needed_domains:
                logger.warning(f"{domain_name} name of {domain} file is not present in the needed domains to be processed list, skipping this file")
                continue

            #Converting DATEDATACHANGED columns values to str
            try:
                dataF['MaxUpdated'] = dataF['MaxUpdated'].fillna('null')
                dataF['MaxUpdated'] = dataF['MaxUpdated'].astype(str)
            except:
                logger.warning(f"The values in the column MaxUpdated cannot be processed")
                pass

            processed_full_df = pd.DataFrame()
            base_cols_present = [col for col in data_columns if col in base_cols]
            item_cols = list(set(data_columns) - set(base_cols_present))
            num_item_cols = len(item_cols)

            #checking whether there are item columns in the data
            if num_item_cols == 0:
                logger.warning(f"There are no item columns in the {domain} file")
                continue

            #Get subject list present
            subject_list = dataF['Subject'].unique().tolist()
            subj_cnt = len(subject_list)
            logger.info(f"Total subjects present in {domain} - {subj_cnt}")

            for i, subject in enumerate(subject_list):
                logger.info(f"RUNNING SUBJECT - {subject} === {i+1}/{subj_cnt}")
                subj_processed_df = pd.DataFrame()
                subj_df = dataF[dataF['Subject'] == subject]
                for ind in tqdm(subj_df.index.tolist()):
                    curr_rec = subj_df.loc[ind, :]
                    base_act_df = pd.DataFrame(curr_rec[base_cols_present].to_dict(), index=[0])
                    final_df = pd.concat([base_act_df] * num_item_cols)
                    answers = list(curr_rec[item_cols].values)
                    final_df['QUESTION'] = item_cols
                    final_df['ANSWER'] = answers
                    subj_processed_df = subj_processed_df.append(final_df, ignore_index=True)
                subj_processed_df['created_dt'] = datetime.datetime.utcnow()
                subj_processed_df['DOMAIN'] = [domain_name for _ in range(len(subj_processed_df))]
                logger.info(f"There are {subj_processed_df.shape[0]} records in {domain} file after unflattening before preprocessing")
                
                #Changing columns name based on the names present in the stg_pred
                subj_processed_df = subj_processed_df.rename(columns=base_cols_rename)
                #Fetching map_tables values
                map_df_dict = rave_utils.get_map_tables(schema=schema, connector=connector)
                
                subj_adpm_df = rave_utils.unflatten_df_process(subj_processed_df, map_df_dict, stg_needed_columns)
                subj_adpm_df = self.process_before_dbinsert(subj_adpm_df, status=status)
                subj_adpm_df.to_csv('subj_adpm_df.csv')
        return subj_adpm_df
