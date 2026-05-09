for jail in $(sudo fail2ban-client status | grep 'Jail list:' | sed 's/.*://;s/,//g'); do
  echo "Jail: $jail";
  sudo fail2ban-client status $jail | grep 'Banned IP';
done
