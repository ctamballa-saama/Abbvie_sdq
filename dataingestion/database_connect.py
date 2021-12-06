import configparser
import datetime
import logging
import getpass
import json
import pyodbc
import sqlalchemy
import traceback
import sys
from datetime import datetime
import os
from sqlalchemy.pool import NullPool

logger = logging.getLogger(os.path.basename(__file__))

def get_connections(connection):
    """Return information about connections"""
    sql = """
    SELECT
        pid,
        state
    FROM pg_stat_activity
    WHERE datname = 'postgres'
    AND query NOT LIKE '%%FROM pg_stat_activity%%'
    """
    rs = connection.execute(sql)
    connections = [
        {"pid": r[0], "state": r[1]} for r in rs.fetchall()
    ]
    return connections

class connection:
    def __init__(self, source, database, config, option = None):
        self.connection = None
        if not config:
            config = configparser.ConfigParser()
            config.read("dataload_configs.ini") 
        else:
            self.config =config  
        self.connectiondetails = self.config[source][database] 
        if not option: # pool_size=2, pool_timeout=60
            self.engine = sqlalchemy.create_engine(self.connectiondetails, poolclass=NullPool, pool_pre_ping=True)
       
    def connect(self, option = None):
        ''' DataBase Connection creation) ''' 
        #close existed connection first 
        if self.connection:
            self.close()    
        if option == 'odbc':
            self.connection = [pyodbc].connect(self.connectiondetails) 
            return  self.connection
        else:
            self.connection = self.engine.connect()
            # try: 
            #     logger.info(self.get_pool_info())
            # except Exception as e:
            #     logger.error(e, 'Fetch database info FAIL.')
            return self.connection 
    
    def close(self):
        try: 
            self.connection.close() 
        except Exception as e:
            pass 

    def get_pool_info(self):
        """Get information about the current connections and pool"""
        return {
            "postgres connections": get_connections(self.connection),
            "pool id": id(self.engine.pool),
            "connections in current pool": (
                self.engine.pool.checkedin() + self.engine.pool.checkedout()
            ),
        }

    def dispose(self): 
        try:
            self.engine.pool.dispose() 
        except Exception as e:
            pass