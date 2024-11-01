let clubs = [];
let map;

async function initMap() {
    mapboxgl.accessToken = 'YOUR_MAPBOX_TOKEN'; // You'll need to get this
    
    map = new mapboxgl.Map({
        container: 'map',
        style: 'mapbox://styles/mapbox/streets-v11',
        center: [34.8516, 31.0461], // Israel's approximate center
        zoom: 7
    });
}

async function loadClubs() {
    try {
        const response = await fetch('../data/clubs.json');
        clubs = await response.json();
        displayClubs(clubs);
    } catch (error) {
        console.error('Error loading clubs:', error);
    }
}

function displayClubs(clubsToShow) {
    const resultsDiv = document.getElementById('results');
    resultsDiv.innerHTML = '';
    
    // Clear existing markers
    document.querySelectorAll('.marker').forEach(marker => marker.remove());
    
    Object.values(clubsToShow).forEach(club => {
        // Add marker to map
        if (club.lat_lng) {
            new mapboxgl.Marker()
                .setLngLat(club.lat_lng)
                .setPopup(new mapboxgl.Popup().setHTML(`
                    <h3>${club.title}</h3>
                    <p>${club.address}</p>
                `))
                .addTo(map);
        }
        
        // Add to results list
        const clubElement = document.createElement('div');
        clubElement.className = 'club-item';
        clubElement.innerHTML = `
            <h3>${club.title}</h3>
            <p>כתובת: ${club.address}</p>
            <p>טלפון: ${club.phone}</p>
            <p>תגיות: ${club.tags.join(', ')}</p>
        `;
        resultsDiv.appendChild(clubElement);
    });
}

function searchClubs() {
    const searchTerm = document.getElementById('search').value.toLowerCase();
    const filteredClubs = Object.fromEntries(
        Object.entries(clubs).filter(([_, club]) => 
            club.title.toLowerCase().includes(searchTerm) ||
            club.address.toLowerCase().includes(searchTerm)
        )
    );
    displayClubs(filteredClubs);
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initMap();
    loadClubs();
}); 
