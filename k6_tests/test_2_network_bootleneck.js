import http from 'k6/http';
import { sleep, check } from 'k6';
import faker from 'k6/x/faker';
import { ServiceDisruptor } from 'k6/x/disruptor';
import { CONFIG, RAMP_UP_SECONDS, FAILURE_DURATION_SECONDS } from './utils/config.js';

// Override the default options to use scenarios
export const options = {
    scenarios: {
        // Scenario 1: Standard load generation
        base_load: {
            executor: 'ramping-vus',
            stages: CONFIG.STANDARD_STAGES,
            exec: 'userTraffic', // Points to the userTraffic function below
        },
        // Scenario 2: Chaos injection
        network_disruption: {
            executor: 'shared-iterations',
            iterations: 1,
            vus: 1,
            exec: 'injectFault',
            startTime: `${RAMP_UP_SECONDS}s`,   // Start after the defined ramp-up phase
        },
    },
    thresholds: {
        http_req_duration: ['p(95)<500'],
    }
};

// ====================================================================
// SCENARIO 1: USER TRAFFIC GENERATOR
// ====================================================================
export function userTraffic() {
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

    const randomEmail = faker.person.email();
    
    http.post(`${CONFIG.BASE_URL}/setCurrency`, { currency_code: 'USD' });
    
    const cartPayload = {
        product_id: 'OLJCESPC7Z',
        quantity: 1,
    };
    
    res = http.post(`${CONFIG.BASE_URL}/cart`, cartPayload);
    check(res, {
        'Product added to cart (200)': (r) => r.status === 200,
    });
    
    sleep(1);

    // Dodany krok: Przejście do kasy, aby wpaść w wąskie gardło (Network Bottleneck)
    const checkoutPayload = {
        email: randomEmail,
        street_address: '123 Observability Way',
        zip_code: '94043', // Amerykański format, by uniknąć błędu 500
        city: 'Cloud City',
        state: 'CA',
        country: 'US',
        credit_card_number: '4111111111111111',
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

// ====================================================================
// SCENARIO 2: CHAOS INJECTION (xk6-disruptor)
// ====================================================================
export function injectFault() {
    // Zmieniony cel ataku: checkoutservice
    console.log('Initiating network disruption: Adding 500ms latency to checkoutservice...');
    
    const disruptor = new ServiceDisruptor('checkoutservice', 'default');
    
    // Failure duration fetched dynamically
    disruptor.injectHTTPFaults({ averageDelay: '500ms' }, `${FAILURE_DURATION_SECONDS}s`);
    
    console.log('Network disruption duration ended. checkoutservice latency returning to normal.');
}
