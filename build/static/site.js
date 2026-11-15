/* The Goods Lane - contact flow.
 * Tapping a Messenger button opens the chat with Ali. A website cannot ask the
 * phone whether Messenger really opened, so we watch for the page being left:
 * if the visitor is still here 2.5s later, or when they come back, a sheet
 * offers WhatsApp with the same message pre-written. Without JavaScript the
 * Messenger and WhatsApp links still work as plain links.
 */
(function () {
  'use strict';
  var sheet = document.getElementById('contact-sheet');
  var waLink = document.getElementById('sheet-whatsapp');
  var msLink = document.getElementById('sheet-messenger');
  var WAIT_MS = 2500;

  function showSheet(messengerUrl, whatsappUrl) {
    if (!sheet || sheet.open) return;
    if (whatsappUrl) waLink.href = whatsappUrl;
    if (messengerUrl) msLink.href = messengerUrl;
    if (typeof sheet.showModal === 'function') sheet.showModal();
    else sheet.setAttribute('open', '');
  }

  document.addEventListener('click', function (event) {
    var link = event.target.closest && event.target.closest('a[data-contact="messenger"]');
    if (!link) return;
    var message = link.getAttribute('data-message');
    if (message && navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(message).catch(function () {});
    }
    var messengerUrl = link.href;
    var whatsappUrl = link.getAttribute('data-whatsapp');
    setTimeout(function () {
      if (!document.hidden) return showSheet(messengerUrl, whatsappUrl);
      var onReturn = function () {
        if (document.hidden) return;
        document.removeEventListener('visibilitychange', onReturn);
        showSheet(messengerUrl, whatsappUrl);
      };
      document.addEventListener('visibilitychange', onReturn);
    }, WAIT_MS);
  });

  if (sheet) {
    sheet.addEventListener('click', function (event) {
      if (event.target === sheet) sheet.close(); // tap on the backdrop
    });
  }
})();
