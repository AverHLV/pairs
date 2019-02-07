function mark(result, id) {
    // send the result of the modal form to the server, then update chosen page elements

    $.getJSON("checked/" + id + "/" + result + "/", function(data) {
        if (data['status'] == "Checked") {
            if (data['code'] == 1) {
                $("#" + id).css('background-color', '#00B64F');
            }

            else {
                $("#" + id).css('background-color', '#A60000');
                $("#" + id + "_r").html(data['reasons'][data['code']]);
            }

            $("#" + id + "_b").html("");
        }
    });
}

function price(result, id) {
    // update order eBay price

    $.getJSON("price/" + id + "/" + result + "/", function(data) {
        if (data['status'] == "Updated") {
            $("#" + id + "_b").html(data['price'] + "$");
            $("#" + id + "_in").html(data['income'] + "$");
            $("#" + id + "_p").html(data['owner'] + ": " + data['profit'] + "$");
        }
    });
}

function modal(reasons, id) {
    // configuration of the modal form

    bootbox.prompt({
        title: "Setting",
        value: "1",
        inputType: "select",

        inputOptions: [
            {
                text: "Mark as checked.",
                value: "1"
            },
            {
                text: "Mark as unsuitable. " + reasons[2],
                value: "2"
            },
            {
                text: "Mark as unsuitable. " + reasons[3],
                value: "3"
            },
            {
                text: "Mark as unsuitable. " + reasons[4],
                value: "4"
            }],

        callback: function(result) {
            if (result !== null) {
                mark(result, id);
            }
        }
    });
}

function modal_price(id, amazon_price) {
    // modal form for order eBay price

    bootbox.prompt({
        title: "eBay price",
        size: "small",

        callback: function(result) {
            if (result === null) {
                return;
            }

            if (result.match(/^\d+\.\d+$/) === null && result.match(/^\d+$/) === null) {
                alert("Please, enter an integer or float number with '.' delimiter.");
                return;
            }

            result = parseFloat(result);
            amazon_price = parseFloat(amazon_price);

            if (!isNaN(result)) {
                if (isNaN(amazon_price)) {
                    alert("Amazon price value is NaN.");
                    return;
                }

                if (result <= 0) {
                    alert("eBay price must be greater than 0.");
                    return;
                }

                if (result >= amazon_price * 0.85) {
                    alert("eBay price must be lower than 85% of Amazon price.");
                    return;
                }

                price(result, id);
            }
        }
    });
}

function set_loader() {
    // load screen setter

    window.scrollTo(0, 0);
    $("body").append('<div style="" id="loadingDiv"><div class="loader">Loading...</div></div>');

    $(window).on('load', function() {
        setTimeout(remove_loader, 0);
    });
}

function remove_loader() {
    // load screen remover

    $("#loadingDiv").fadeOut(0, function() {
        $("#loadingDiv").remove();
    });
}