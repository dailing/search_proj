Vue.use(AsyncComputed)

var app = new Vue({
    el: "#app",
    data: {
        canvas: null,
        ctx: null,
        image: null,

        search_text: '',
        search_result:[],

        current_box: -1,
        boxes: [],
        adding_box: false,

        file_to_upload: null,

        current_image: null,

        current_page: 1,
        images_per_page: 9,
        num_page: 0,
        images_this_page: [],

        sessions: [],
        current_session: { "session_name": 'null' },

        new_session_name: null,

        show_existing_images: false,
        papers: [],
        paper_info: {},
    },
    methods: {
        get_papers: function() {
            Vue.http.get('/api/list/paper', {}).then(response => {
                this.papers = response.data.items
            })
        },
        _format_size: function(size){
            console.log(size);
            units = 'BKMGT';
            cnt = 0;
            size = parseInt(size);
            while (size >= 1000){
                cnt += 1;
                size /= 1024;
            }
            size = Math.round(size * 100) / 100;
            return size + units[cnt];
        },
        search_doc: function() {
            console.log('search doc:' + this.search_text);
            cfg = {
                params: {
                    kw:this.search_text,
                    mode:'search'
                }
            }
            Vue.http.get(
                '/filemanager/api', cfg
            ).then(response => {
                data = response.data;
                console.log(data);
                this.search_result = data;
            })
        },
        search: function() {
            console.log('search');
            Vue.http.post(
                "/api/search",
                this.paper_info.title,
            ).then(response => {
                console.log(response.data);
                this.paper_info = response.data;
            })
        },
        _add_boxes: function(box_xywh) {
            var box = new Box();
            box.x = box_xywh[1] * this.canvas.width;
            box.width = box_xywh[3] * this.canvas.width;
            box.y = box_xywh[0] * this.canvas.height;
            box.height = box_xywh[2] * this.canvas.height;
            this.boxes.push(box);
            return box;
        },
        handleNewImage: function(record) {
            this.current_image = record;
            // set image
            url = record.url;
            var img = new Image();
            img.onload = function() {
                const width = 500;
                console.log(this);
                console.log(this.width);
                app.canvas.height = Math.floor(app.canvas.width / this.width * this.height)
                app.render();
            };
            img.src = url;
            this.image = img;
            // add boxes
            if (this.show_existing_images) {
                Vue.http.get(
                    '/api/annotation/' + this.current_image.id
                ).then(response => {
                    console.log(response.data);
                    app.boxes = [];
                    for (var i = 0; i < response.data.length; i += 1) {
                        var box = app._add_boxes(response.data[i].points)
                        box.record = response.data[i];
                    }
                    app.render();
                })
            } else {
                Vue.http.get(
                    '/api/get_result/' + this.current_image.id
                ).then(response => {
                    console.log(response.data);
                    app.boxes = [];
                    for (var i = 0; i < response.data.result.length; i += 1) {
                        console.info(response.data.result[i])
                        var box = app._add_boxes(response.data.result[i].box_xywh)
                        box.detect = response.data[i];
                    }
                    app.render();
                });
            }
        },
        render: function() {
            if (this.image != null) {
                this.canvas.height = Math.floor(this.canvas.width / this.image.width * this.image.height);
                this.ctx.drawImage(this.image, 0, 0, this.canvas.width, this.canvas.height);
            }
            for (var i = 0; i < this.boxes.length; i += 1) {
                this.ctx.save();
                this.ctx.strokeStyle = "green";
                if (this.current_box < 0) {
                    if (this.boxes[i]._boder) {
                        this.ctx.strokeStyle = 'red';
                    } else if (this.boxes[i]._in) {
                        this.ctx.fillStyle = 'rgba(0, 255, 0, 0.2)';
                        this.ctx.fillRect(...this.boxes[i].top_left);
                    }
                }
                if (this.selected_box == i) {
                    this.ctx.setLineDash([2, 2]);
                }
                this.ctx.strokeRect(
                    ...this.boxes[i].top_left
                );
                this.ctx.restore();
            }
        },
        handle_mouse_event(event) {
            if (this.adding_box) {
                if (event.type == 'mousedown') {
                    console.log(event);
                    this.adding_box = false;
                    newbox = new Box();
                    newbox.x = event.offsetX;
                    newbox.y = event.offsetY;
                    newbox.mouse_down_event = event;
                    newbox.status = 20;
                    newbox.dx = 1;
                    newbox.dy = 1;
                    this.boxes.push(newbox)
                }
            }
            if (this.current_box < 0) {
                for (var i = 0; i < this.boxes.length; i += 1) {
                    if (this.boxes[i].handleEvent(event)) {
                        this.current_box = i;
                        this.selected_box = i;
                        break;
                    }
                }
            } else {
                if (!this.boxes[this.current_box].handleEvent(event)) {
                    this.current_box = -1;
                }
            }
            event.preventDefault();
            this.render();
        },
        _normal_post_data: function name(url, form_data) {
            form_data.set('session_name', this.current_session.session_name)
            Vue.http.post(url, form_data).then(response => {
                console.log(response);
            }, response => {
                console.log(response);
            });
        },
        submit: function() {
            console.log('submit!');
            var form_data = new FormData();
            for (var i = 0; i < this.file_to_upload.length; i += 1) {
                form_data.append(i, this.file_to_upload[i])
                if (i != 0 && i % 10 == 0) {
                    this._normal_post_data('/api/add_img', form_data);
                    form_data = new FormData();
                }
            }
            if (i % 10 != 0) {
                this._normal_post_data('/api/add_img', form_data);
            }
        },
        submit_anno: function() {
            console.log('submit annotation');
            var post_data = [];
            for (var i = 0; i < this.boxes.length; i += 1) {
                var bbox = this.boxes[i].bbox;
                bbox[0] /= this.canvas.width;
                bbox[2] /= this.canvas.width;
                bbox[1] /= this.canvas.height;
                bbox[3] /= this.canvas.height;
                bbox = [bbox[1], bbox[0], bbox[3], bbox[2]];
                var rec = null;
                if (this.boxes[i].record != null) {
                    rec = this.boxes[i].record;
                    rec.points = bbox;
                } else {
                    rec = {
                        image_id: this.current_image.id,
                        session_name: this.current_image.session_name,
                        points: bbox,
                    };
                }
                post_data.push(rec);
            }
            if (post_data.length == 0) {
                post_data.push({
                    image_id: this.current_image.id,
                    session_name: this.current_image.session_name,
                    points: [-1, -1, -1, -1],
                });
            }
            console.log(post_data);
            Vue.http.post('/api/annotation', post_data).then(
                response => {
                    console.log(response.data);
                    app._update_images_this_page();
                }, response => {
                    console.log(response.data);
                }
            );
        },
        _keyboard_event: function(event) {
            console.log(event);
            if (event.key == "d") {
                this.remove_selected();
            } else if (event.key == 'a') {
                this.adding_box = true;
            } else if (event.key == 's') {
                this.adding_box = false;
            } else if (event.key == 'q') {
                this.selected_box = (this.selected_box + 1) % this.boxes.length;
            } else if (event.key == 'w') {
                this.submit_anno();
            }
            this.render();
        },
        _update_images_this_page() {
            var url = '/api/image_list/' + this.current_session.session_name + '/' + this.current_page + '/' + this.images_per_page;
            if (this.show_existing_images) {
                url = '/api/image_list_existing/' + this.current_session.session_name + '/' + this.current_page + '/' + this.images_per_page;
            }
            Vue.http.get(url)
                .then(response => {
                    console.log(response.data);
                    this.num_page = response.data.num_page;
                    this.images_this_page = response.data.result;
                    this.handleNewImage(this.images_this_page[0]);
                    return response.data.result;
                })
        }
    },
    asyncComputed: {
        // images_this_page() {
        //     this._update_images_this_page();
        // },
    },
    computed: {

    },
    watch: {
        // image_to_annotate: function(val) {
        // }
    },
    mounted() {
        // this.canvas = document.getElementById('canvas');
        // this.canvas.onmousedown = this.handle_mouse_event;
        // this.canvas.onmouseup = this.handle_mouse_event;
        // this.canvas.onmousemove = this.handle_mouse_event;
        // this.canvas.oncontextmenu=this.n;
        // this.ctx = this.canvas.getContext('2d');
        // document.addEventListener("keydown", function(event){
        //     app._keyboard_event(event);
        // }, false);
        // this.update_session();
        // this.get_papers();
        console.log('init!')
    }
});