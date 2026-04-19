// k6_tests/utils/config.js

export const RAMP_UP_SECONDS = 120;
export const FAILURE_DURATION_SECONDS = 180;

export const CONFIG = {
    BASE_URL: 'http://150.254.32.183:30080',
    
    // Define load phases manually as needed
    STANDARD_STAGES: [
        { duration: '2m', target: 50 },
        { duration: '10m', target: 50 },
        { duration: '1m', target: 0 }, 
    ],

    STANDARD_THRESHOLDS: {
        http_req_failed: ['rate<0.01'],
        http_req_duration: ['p(95)<500'],
    }
};