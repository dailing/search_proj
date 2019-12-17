Vue.use(AsyncComputed)


// usage: {{ file.size | prettyBytes }}
Vue.filter('prettyBytes', function(num) {
    // jacked from: https://github.com/sindresorhus/pretty-bytes
    if (typeof num !== 'number' || isNaN(num)) {
        return 'Nan';
        throw new TypeError('Expected a number');
    }

    var exponent;
    var unit;
    var neg = num < 0;
    var units = ['B', 'kB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'];

    if (neg) {
        num = -num;
    }

    if (num < 1) {
        return (neg ? '-' : '') + num + ' B';
    }

    exponent = Math.min(Math.floor(Math.log(num) / Math.log(1000)), units.length - 1);
    num = (num / Math.pow(1000, exponent)).toFixed(2) * 1;
    unit = units[exponent];

    return (neg ? '-' : '') + num + ' ' + unit;
});



var app = new Vue({
    el: "#app",
    data: {
        path: '',
        info: {},
        _search_kw_mapping: [
            ['abstract', 'abstract'],
            ['author', 'author'],
            ['journal', 'journal'],
            ['title', 'title']
        ],
    },
    methods: {
        getUrlVars: function() {
            var vars = {};
            var parts = window.location.href.replace(/[?&]+([^=&]+)=([^&]*)/gi, function(m, key, value) {
                vars[key] = value;
            });
            return vars;
        },
        search_xueshu: function(query) {
            var result = Vue.http.get(
                "/api/search?query=" + query,
            ).then(resp => {
                data = resp.data
                console.log(data);
                for(var i =0; i < app._data._search_kw_mapping.length; i+=1){
                    search_kw = app._data._search_kw_mapping[i][0]
                    record_kw = app._data._search_kw_mapping[i][1]
                    if(search_kw in data){
                        app._data.info.meta_info[record_kw] = data[search_kw];
                    }
                }
            });
        },
        save: function(){
            Vue.http.put(
                '/api/item/paper/' + this.info.meta_info.id,
                this.info.meta_info
            ).then(response => {
                console.log(response);
                this.info = response.data;
            })
    
        },
        _init: function(){
            this.path = this.getUrlVars()['path'];
            Vue.http.get(
                '/api/item/file/' + this.path
            ).then(response => {
                console.log(response.data);
                this.info = response.data;
                if (this.info.meta_info.title === null){
                    this.info.meta_info.title = this.info.name.split('.')[0];
                }
            });    
        }
    },
    mounted() {
        console.log('init!');
        this._init();   
    }

})