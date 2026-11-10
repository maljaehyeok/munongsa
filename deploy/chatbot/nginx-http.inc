# Include only inside the existing http block. Do not duplicate existing zones.
limit_req_zone $binary_remote_addr zone=munongsa_chat_rate:1m rate=10r/m;
limit_conn_zone $binary_remote_addr zone=munongsa_chat_conn:1m;
