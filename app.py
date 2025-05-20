import uvicorn

# Format logs
log_config = uvicorn.config.LOGGING_CONFIG
log_config['formatters']['access'][
    'fmt'
] = '%(asctime)s - %(levelname)s - %(message)s'
log_config['formatters']['default'][
    'fmt'
] = '%(asctime)s - %(levelname)s - %(message)s'
log_config['formatters']['default']['datefmt'] = '%Y-%m-%d %H:%M:%S'
log_config['formatters']['access']['datefmt'] = '%Y-%m-%d %H:%M:%S'

if __name__ == '__main__':
    uvicorn.run(
        'src:app',
        port=3001,
        reload=True,
        host='0.0.0.0',
        proxy_headers=True,
        workers=1,
        forwarded_allow_ips='*',
    )
