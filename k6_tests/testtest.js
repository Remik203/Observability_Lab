import http from 'k6/http';
import { check } from 'k6';
import { CONFIG } from './utils/config.js';

// Nadpisujemy opcje na sztywno - bardzo krótki test
export const options = {
    vus: 5,           // Tylko 5 wirtualnych użytkowników naraz
    duration: '10s',  // Ogień tylko przez 10 sekund
};

export default function () {
    // Proste zapytanie GET w stronę główną sklepu
    let res = http.get(`${CONFIG.BASE_URL}/`);
    
    // Sprawdzamy tylko, czy serwer odpowiada kodem 200 (OK)
    check(res, {
        'Serwer zyje i odpowiada 200 OK': (r) => r.status === 200,
    });
}