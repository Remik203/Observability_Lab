import http from 'k6/http';
import { sleep, check } from 'k6';
import { CONFIG } from './utils/config.js';
import faker from 'k6/x/faker';

// Load test options from the configuration file
export const options = {
    stages: CONFIG.STANDARD_STAGES,
    thresholds: CONFIG.STANDARD_THRESHOLDS,
};

// ====================================================================
// MAIN VIRTUAL USER SCENARIO
// ====================================================================
export default function () {
    // 1. Visit the main page
    let res = http.get(`${CONFIG.BASE_URL}/`);
    check(res, {
        'Main page responds with 200': (r) => r.status === 200,
    });
    
    // Simulate user reading the page
    sleep(Math.random() * 2 + 1);

    // 2. Visit a specific product page (eg. Watch)
    res = http.get(`${CONFIG.BASE_URL}/product/1YMWWN1N4O`);
    check(res, {
        'Product page responds with 200': (r) => r.status === 200,
    });
    
    sleep(Math.random() * 2 + 1);

    // 3. Set currency and add the product to the cart
    const randomEmail = faker.person.email();
    
    http.post(`${CONFIG.BASE_URL}/setCurrency`, { currency_code: 'USD' });
    
    const cartPayload = {
        product_id: '1YMWWN1N4O',
        quantity: 1,
    };
    
   res = http.post(`${CONFIG.BASE_URL}/cart`, cartPayload);
    check(res, {
        'Product added to cart (200)': (r) => r.status === 200,
    });
    
    sleep(Math.random() * 2 + 1);

    // 4. Checkout process
    const checkoutPayload = {
        email: 'test@example.com',
        street_address: 'Poznańska 21/37',
        zip_code: '60820',
        city: 'Poznań',
        state: 'Wielkopolskie',
        country: 'PL',
        credit_card_number: '4111111111111111', //Official Test Credit Card Account Numbers - paypalobjects.com
        credit_card_expiration_month: '12',
        credit_card_expiration_year: '2030',
        credit_card_cvv: '123'
    };
    
    res = http.post(`${CONFIG.BASE_URL}/cart/checkout`, checkoutPayload);
    check(res, {
        'Checkout successful (200)': (r) => r.status === 200,
    });
    
    sleep(2);
}