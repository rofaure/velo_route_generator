(function () {
    var hostname = window.location.hostname;
    var origin = window.location.protocol + '//' + hostname + (window.location.port ? ':' + window.location.port : '');

    BR.conf = {};
    BR.conf.transit = false;

    // Moteur BRouter local (conteneur brouter, port 17777)
    BR.conf.host = 'http://localhost:17777';
    // Profils servis par le conteneur web (dossier ./profiles monte en /profiles2)
    BR.conf.profilesUrl = origin + '/profiles2/';

    BR.conf.appName = 'BRouter-Web (local)';
    BR.conf.privacyPolicyUrl = '/privacypolicy.html';

    // Ouvre la carte sur Saint-Cergues
    BR.conf.initialMapLocation = [46.2315, 6.3186];
    BR.conf.initialMapZoom = 13;

    // Profils proposes dans le menu (fichiers .brf presents dans ./profiles)
    BR.conf.profiles = ['roadonly', 'fastbike'];
    BR.conf.profilesRename = {};

    BR.conf.clearBaseLayers = false;
    BR.conf.baseLayers = {};
    BR.conf.defaultBaseLayerIndex = 0;
    BR.conf.defaultOpacity = 0.67;
    BR.conf.minOpacity = 0.3;

    BR.conf.routingStyles = {
        trailer: { weight: 5, dashArray: [10, 10], opacity: 0.6, color: 'magenta' },
        track: { weight: 5, color: 'magenta', opacity: BR.conf.defaultOpacity },
        trackCasing: { weight: 8, color: 'white', opacity: BR.conf.defaultOpacity },
        nodata: { color: 'darkred' },
        beeline: { weight: 5, dashArray: [1, 10], color: 'magenta', opacity: BR.conf.defaultOpacity },
        beelineTrailer: { weight: 5, dashArray: [1, 10], opacity: 0.6, color: 'magenta' },
    };

    BR.conf.markerColors = { poi: '#436978', start: '#72b026', via: '#38aadd', stop: '#d63e2a' };
    BR.conf.tracknameAllowedChars = 'a-zA-Z0-9 \\._\\-';
    BR.conf.overpassBaseUrl = 'https://overpass.kumi.systems/api/interpreter';
    BR.conf.trackSizeLimit = 1024 * 10;
})();
