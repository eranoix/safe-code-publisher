// Receipt mailer. One template, plain text, no attachments.
function receipt(config, customer, rental) {
  return {
    from: config.mail.from,
    to: customer.email,
    subject: `${config.site.name} — receipt for rental #${rental.id}`,
    text: [
      `Hi ${customer.name},`,
      "",
      `Thanks for renting from ${config.site.name}.`,
      `Bike: ${rental.bike}  •  ${rental.days} day(s)  •  ${rental.total} EUR`,
      `Deposit held: ${rental.deposit} EUR`,
      "",
      `Questions? Call us on ${config.site.supportPhone} or reply to this mail.`,
      `${config.site.publicUrl}`,
    ].join("\n"),
  };
}

module.exports = { receipt };
