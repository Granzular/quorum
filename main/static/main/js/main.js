// Mobile menu toggle
const menuToggle = document.querySelector('.menu-toggle');
const navList = document.querySelector('.nav-list');

menuToggle.addEventListener('click', () => {
    navList.classList.toggle('active');
    menuToggle.classList.toggle('active');
});

// Close menu when clicking a link
navList.querySelectorAll('a').forEach(link => {
    link.addEventListener('click', () => {
        navList.classList.remove('active');
        menuToggle.classList.remove('active');
    });
});

// Optional: Close menu when clicking outside
document.addEventListener('click', (e) => {
    if (!e.target.closest('.nav') && navList.classList.contains('active')) {
        navList.classList.remove('active');
        menuToggle.classList.remove('active');
    }
});

// Search logic
searchBtn = document.querySelector('#search-btn');
searchBox = document.querySelector('#search-box');
searchBtn.addEventListener('click',searchFunction,false);
searchBox.addEventListener('keydown',(event)=>{if(event.key == 'Enter'){searchFunction(event)}},false);


    function searchFunction(event){

        query = document.querySelector('#search-box').value;
        params = new URLSearchParams({
            'name' : query,
        })
        fetch(`/api/library/resources/search/?${params}`)
        .then((res)=>{
            if (res.ok){
                return res.json()
            }
            else{
             resBox = document.querySelector('#search-result');
             resBox.innerHTML = `<div style='color:red;'>An error occured. status: ${res.status} </div>`
             return res.json()
            }
        })
        .then((data)=>{
            resBox = document.querySelector('#search-result')
            buffer = '<ul>'
            for (item of data.data){
                buffer += `<li class='search-result-item'>${item.name}<br>
                <a class='preview-link' href='${item.preview_url}'>preview</a> | 
                <a #download-link href='${item.download_url}'>download</a></li><br>`
            }
            if(data.length == 0){
                buffer += '<p>query returned no result</p>';
            }
            buffer += '</ul>';
            resBox.innerHTML = buffer;
            return data
        })
    }

    // Comment Logic
    

    // Like logic
    
    // Data sync logic
    document.querySelector('#data-sync-btn').addEventListener('click',
        (event)=>{
            event.target.setAttribute('disabled','true')
            fetch('/sync/')
            .then((res)=> event.target.removeAttribute('disabled'))
        }
        ,false)