const fs = require('fs');

(() => {
	console.log(fs.readFileSync('./file.txt', 'utf8'));
	console.log(__dirname)
})();
