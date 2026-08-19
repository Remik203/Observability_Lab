import http from 'k6/http';
import { sleep, check } from 'k6';
import faker from 'k6/x/faker';
import exec from 'k6/execution';
import { CONFIG, WAIT_BEFORE_FAILURE_SECONDS, FAILURE_DURATION_SECONDS } from './utils/config.js';

export const options = {
    stages: CONFIG.STANDARD_STAGES,
    thresholds: {
        http_req_duration: ['p(95)<500'],
        http_req_failed: ['rate<=1.0'],
    }
};

export default function () {
    let res = http.get(`${CONFIG.BASE_URL}/`);
    check(res, {
        'Main page responds with 200': (r) => r.status === 200,
    });
    sleep(Math.random() * 2 + 1);

    res = http.get(`${CONFIG.BASE_URL}/product/OLJCESPC7Z`);
    check(res, {
        'Product page responds with 200': (r) => r.status === 200,
    });
    sleep(Math.random() * 2 + 1);

    // Obliczenie upływu czasu i stworzenie "okna awarii"
    const elapsedSeconds = (new Date() - exec.scenario.startTime) / 1000;
    const isFailureWindow = elapsedSeconds >= WAIT_BEFORE_FAILURE_SECONDS && 
                            elapsedSeconds <= (WAIT_BEFORE_FAILURE_SECONDS + FAILURE_DURATION_SECONDS);

    // 20% wirtualnych użytkowników wyśle zatruty payload, ALE TYLKO w oknie awarii
    const isPoisoned = isFailureWindow && (Math.random() < 0.20);
    
    let cartPayload;
    if (isPoisoned) {
        cartPayload = { product_id: 'POISON_ITEM_INVALID_500', quantity: 1 };
    } else {
        cartPayload = { product_id: 'OLJCESPC7Z', quantity: 1 };
    }

    http.post(`${CONFIG.BASE_URL}/setCurrency`, { currency_code: 'USD' });
    
    res = http.post(`${CONFIG.BASE_URL}/cart`, cartPayload);
    
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
