// k6_tests/utils/config.js

export const WAIT_BEFORE_FAILURE_SECONDS = 240;
export const FAILURE_DURATION_SECONDS = 120;

export const CONFIG = {
    BASE_URL: `http://${__ENV.TARGET_IP || '127.0.0.1'}:30080`,
    
    STANDARD_STAGES: [
        { duration: '1m', target: 50 }, // Wzrost do 50
        { duration: '8m', target: 50 }, // Utrzymanie 50 (w trakcie tego dzieje się awaria)
        { duration: '1m', target: 0 },  // Spadek do 0
    ],

    STANDARD_THRESHOLDS: {
        http_req_failed: ['rate<0.01'],
        http_req_duration: ['p(95)<500'],
    }
};
