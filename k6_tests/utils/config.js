// k6_tests/utils/config.js

export const CONFIG = {
    BASE_URL: 'http://150.254.32.183:30080',
    
    // Standardowe fazy obciążenia (tzw. ramp-up, utrzymanie i ramp-down)
    // To wygeneruje płynny ruch, idealny do mierzenia "szumu tła" i zasobów
    STANDARD_STAGES: [
        { duration: '2m', target: 50 },
        { duration: '10m', target: 50 },
        { duration: '1m', target: 0 }, 
    ],

    // Progi zaliczenia testu
    STANDARD_THRESHOLDS: {
        http_req_failed: ['rate<0.01'],
        http_req_duration: ['p(95)<500'],
    }
};