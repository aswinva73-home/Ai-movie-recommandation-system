
function saveHistory(movie){

    fetch('/save_history', {
        method:'POST',
        headers:{
            'Content-Type':'application/x-www-form-urlencoded'
        },
        body:'movie=' + movie
    });
}

const searchInput = document.getElementById("searchInput");

searchInput.addEventListener("keyup", function(){

    let filter = searchInput.value.toLowerCase();

    let cards = document.querySelectorAll(".movie-card");

    cards.forEach(card => {

        let title = card.innerText.toLowerCase();

        if(title.includes(filter)){
            card.style.display = "block";
        }
        else{
            card.style.display = "none";
        }

    });

});
