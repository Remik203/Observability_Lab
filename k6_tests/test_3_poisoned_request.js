import http from 'k6/http';
import { sleep, check } from 'k6';
import faker from 'k6/x/faker';
import { CONFIG } from './utils/config.js';

// Override default options. 
// Reduced the http_req_failed threshold because this test intentionally generates HTTP 500 errors.
export const options = {
    stages: CONFIG.STANDARD_STAGES,
    thresholds: {
        http_req_duration: ['p(95)<500'],
    }
};

// ====================================================================
// MAIN VIRTUAL USER SCENARIO: POISONED REQUEST INJECTION
// ====================================================================
export default function () {
    // 1. Visit the main page
    let res = http.get(`${CONFIG.BASE_URL}/`);
    check(res, {
        'Main page responds with 200': (r) => r.status === 200,
    });
    
    sleep(Math.random() * 2 + 1);

    // 2. Visit a specific product page (Normal behavior)
    res = http.get(`${CONFIG.BASE_URL}/product/OLJCESPC7Z`);
    check(res, {
        'Product page responds with 200': (r) => r.status === 200,
    });
    
    sleep(Math.random() * 2 + 1);

    // 3. Chaos Branching Logic
    // 20% of the virtual users will inject a poisoned payload
    const isPoisoned = Math.random() < 0.20;
    let cartPayload;

    if (isPoisoned) {
        console.log('Injecting poisoned request: Invalid product ID sent to cart');
        cartPayload = {
            product_id: 'POISON_ITEM_INVALID_500',
            quantity: 1,
        };
    } else {
        cartPayload = {
            product_id: 'OLJCESPC7Z',
            quantity: 1,
        };
    }

    // Set currency context
    http.post(`${CONFIG.BASE_URL}/setCurrency`, { currency_code: 'USD' });
    
    // Send the POST request to the cart
    res = http.post(`${CONFIG.BASE_URL}/cart`, cartPayload);
    
    // Check responses based on user path
    if (isPoisoned) {
        check(res, {
            'Poisoned request generated error (500)': (r) => r.status >= 500,
        });
    } else {
        check(res, {
            'Product added to cart (200)': (r) => r.status === 200,
        });
    }
    
    sleep(2);
}